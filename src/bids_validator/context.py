"""Classes and functions for populating a validation context."""

from __future__ import annotations

import gzip
import math
import struct
import zlib
from functools import cache

import attrs
import nibabel as nb
import orjson
from bidsschematools.types import context as ctx
from bidsschematools.types.namespace import Namespace
from upath import UPath

from .types import _typings as t
from .types.files import FileTree

# The same trick as ``typing.TYPE_CHECKING``, without importing ``typing``: False when
# the program runs, so the imports below are only seen by type checkers (mypy, pyright).
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import TypeVar

    from bidsschematools.types import protocols as proto

    # pyright does not treat cached_property like property
    cached_property = property

    ImgT = TypeVar('ImgT', bound=nb.filebasedimages.FileBasedImage)
else:
    from functools import cached_property


# Design strategy for these classes.
#
# *  Attribute access is essential. Dictionary lookups must become either
#    dataclasses or Namespace-like objects.
# *  Objects should have a single source of truth, such as a FileTree object.
#    When defining derived fields, prefer @property if the lookup is trivial
#    or cached_property, if it is nontrivial.
# *  Hitting the filesystem should be minimized. FileTree already caches os.stat calls,
#    but reading file contents should never happen more than once. Therefore, if file
#    contents are accessed in the context.associations or context.dataset, they should
#    use caching loaders.
# *  If the full contents of an object will be known on its first instantiation,
#    prefer to use the dataclasses in bidsschematools.types.context. Lazy fields
#    need custom classes.


class ValidationError(Exception):
    """A problem found while reading a file, with the code it is reported under.

    Attributes
    ----------
    code : str
        An issue code (``JSON_INVALID``, ``TSV_EQUAL_ROWS``, ``MULTIPLE_INHERITABLE_FILES``
        ...), so a check can turn the error into a finding without knowing which
        loader raised it.
    message : str or None
        Detail for the finding.
    line : int or None
        The 1-based line of a table problem.
    location : str or None
        Dataset-relative path of the file the problem belongs to, when that is not the
        file being read (an ambiguous sidecar is reported on the sidecar).

    """

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        line: int | None = None,
        location: str | None = None,
    ):
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.line = line
        self.location = location


class FileContents(dict[str, t.Any]):
    """The contents of a file (a JSON object, a table's columns) with attribute access.

    Like a bidsschematools ``Namespace``, a field can be read as ``contents.Field``.
    Unlike one, a key is only ever a key. A ``Namespace`` reads ``"key_resp.rt"`` as a
    path into nested objects and cannot even list a mapping that holds such a key,
    and table columns written by tools such as PsychoPy contain dots.
    """

    # Called for ``contents.Field`` when ``Field`` is not a normal attribute: read it as
    # the key ``'Field'``. The expression language reads ``sidecar.RepetitionTime`` so.
    def __getattr__(self, name: str) -> t.Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def to_dict(self) -> dict[str, t.Any]:
        """Return a plain ``dict`` copy."""
        return dict(self)


# Datatype -> modality (``anat`` -> ``mri``), filled from the schema on first use by
# ``datatype_to_modality``.
_DATATYPE_MAP: dict[str, str] = {}

# Rows of a table read for the checks: the reference validator's ``--max-rows``
# default. A physiology recording can have millions of rows; the first thousand show
# whether its values have the right type.
TSV_MAX_ROWS = 1000


def datatype_to_modality(datatype: str, schema: Namespace) -> str | None:
    """Generate a global map for datatype to modality.

    Returns None for a datatype that belongs to no modality. ``phenotype`` is one:
    it is a datatype in ``objects.datatypes`` but appears in no ``rules.modalities``
    entry, so a dataset with a ``phenotype/`` folder used to raise ``KeyError`` here.
    """
    global _DATATYPE_MAP
    if not _DATATYPE_MAP:
        for mod_name, mod_dtypes in schema.rules.modalities.items():
            _DATATYPE_MAP |= dict.fromkeys(mod_dtypes['datatypes'], mod_name)
    return _DATATYPE_MAP.get(datatype)


def _read_columns(
    lines: t.Iterable[str], headers: list[str], *, max_rows: int, first_line: int
) -> FileContents:
    """Split table rows into columns, enforcing the shape the reference validator does.

    A row with a different number of cells than there are headers raises
    ``TSV_EQUAL_ROWS``; an empty line raises ``TSV_EMPTY_LINE``, unless it is the last
    line, since a file is expected to end with a newline. ``first_line`` is the
    1-based number of the first row in the file, for the error's ``line``.
    """
    rows: list[list[str]] = []
    pending_empty: int | None = None
    for number, line in enumerate(lines, start=first_line):
        if max_rows > 0 and len(rows) >= max_rows:
            break
        text = line.rstrip('\r\n')
        if pending_empty is not None:
            raise ValidationError('TSV_EMPTY_LINE', line=pending_empty)
        if text == '':
            pending_empty = number
            continue
        values = text.split('\t')
        if len(values) != len(headers):
            raise ValidationError(
                'TSV_EQUAL_ROWS',
                f'{len(values)} values for {len(headers)} columns',
                line=number,
            )
        rows.append(values)
    return FileContents(
        (header, tuple(row[index] for row in rows)) for index, header in enumerate(headers)
    )


@cache
def load_tsv(file: FileTree, *, max_rows: int = 0) -> FileContents:
    """Load TSV contents into columns, keyed by header.

    A UTF-8 byte order mark is dropped. Raises :class:`ValidationError` with the code
    the reference validator reports: ``TSV_COLUMN_HEADER_DUPLICATE``,
    ``TSV_EMPTY_LINE`` or ``TSV_EQUAL_ROWS``. A header with no rows gives empty
    columns, not a missing one.
    """
    with file.path_obj.open(encoding='utf-8-sig', newline='') as fobj:
        lines = iter(fobj)
        header_line = next(lines, '').rstrip('\r\n')
        headers = header_line.split('\t') if header_line else []
        if len(set(headers)) != len(headers):
            raise ValidationError('TSV_COLUMN_HEADER_DUPLICATE', ', '.join(headers))
        return _read_columns(lines, headers, max_rows=max_rows, first_line=2)


@cache
def load_tsv_gz(file: FileTree, headers: tuple[str], *, max_rows: int = 0) -> FileContents:
    """Load a headerless, gzipped TSV, whose headers come from its sidecar's ``Columns``.

    Raises :class:`ValidationError`: ``INVALID_GZIP`` when it does not decompress,
    and the shape errors of :func:`load_tsv`.
    """
    try:
        with file.path_obj.open('rb') as fobj, gzip.GzipFile(fileobj=fobj, mode='r') as gzobj:
            lines = (line.decode('utf-8') for line in gzobj)
            return _read_columns(lines, list(headers), max_rows=max_rows, first_line=1)
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise ValidationError('INVALID_GZIP', str(error)) from error


@cache
def load_json(file: FileTree) -> FileContents:
    """Load the contents of a JSON file.

    Raises :class:`ValidationError` with the code the reference validator reports:
    ``INVALID_JSON_ENCODING`` (not UTF-8, or UTF-8 with a byte order mark, which JSON
    forbids), ``JSON_INVALID`` (does not parse) or ``JSON_NOT_AN_OBJECT``.
    """
    data = file.path_obj.read_bytes()
    if data.startswith(b'\xef\xbb\xbf'):
        raise ValidationError('INVALID_JSON_ENCODING', 'starts with a byte order mark')
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValidationError('INVALID_JSON_ENCODING', str(error)) from error
    try:
        contents = orjson.loads(data)
    except orjson.JSONDecodeError as error:
        raise ValidationError('JSON_INVALID', str(error)) from error
    if not isinstance(contents, dict):
        raise ValidationError('JSON_NOT_AN_OBJECT', type(contents).__name__)
    return FileContents(contents)


# What nibabel raises for an empty, truncated or mislabelled image, plus the TypeError
# load_image raises for an image that is not NIfTI-1.
NIFTI_LOAD_ERRORS = (nb.filebasedimages.ImageFileError, OSError, EOFError, ValueError, TypeError)


def load_image(path: UPath, api: type[ImgT]) -> ImgT:
    """Load neuroimaging file with a given nibabel API."""
    img = nb.load(path)  # type: ignore[arg-type]
    if not isinstance(img, api):
        raise TypeError(f'Expected image of type {api}, got {type(img)}')
    return img


def load_nifti_header(file: FileTree) -> ctx.NiftiHeader:
    """Load NIfTI header contents."""
    img = load_image(file.path_obj, nb.nifti1.Nifti1Image)

    # Nibabel uses None,0,1,2, BIDS context uses 1,2,3 with 0 as absent
    freq, phase, slc = (
        dim + 1 if dim is not None else 0
        for dim in img.header.get_dim_info()  # type: ignore[no-untyped-call]
    )
    dim_info = ctx.DimInfo(freq, phase, slc)

    xyz, t = img.header.get_xyzt_units()  # type: ignore[no-untyped-call]
    if t not in ('unknown', 'sec', 'msec', 'usec'):
        # The NIfTI standard allows for 'Hz', 'ppm' and 'rads', but BIDS currently
        # considers temporal units.
        t = 'unknown'
    xyzt_units = ctx.XyztUnits(xyz, t)

    try:
        mrs_header = next(ext for ext in img.header.extensions if ext.get_code() == 44)
        mrs_meta = Namespace(mrs_header.json())
    except StopIteration:
        mrs_meta = None

    nifti_header = ctx.NiftiHeader(
        dim_info=dim_info,
        dim=img.header['dim'],
        pixdim=img.header['pixdim'],
        shape=img.shape,
        voxel_sizes=img.header.get_zooms(),  # type: ignore[no-untyped-call]
        xyzt_units=xyzt_units,
        qform_code=int(img.header['qform_code']),
        sform_code=int(img.header['sform_code']),
        axis_codes=nb.orientations.aff2axcodes(img.affine),  # type: ignore[no-untyped-call]
        mrs=mrs_meta,
    )

    return nifti_header


def load_gzip_header(file: FileTree) -> ctx.Gzip | None:
    """Load gzip header fields.

    Reference: https://www.rfc-editor.org/info/rfc1952/
    """
    try:
        with file.path_obj.open('rb') as fobj:
            # Constant header fields: ID1, ID2, CM, FLG, MTIME, XFL, OS
            magic, flags, timestamp = struct.unpack('<HxBIxx', fobj.read(10))
            if magic != 0x8B1F:
                return None

            if flags & 0b0_0100:  # FEXTRA
                size = int.from_bytes(fobj.read(2), 'little')
                fobj.seek(size, 1)  # Skip extra field

            # Fetch enough header to include filename and at least the start of comment.
            # Buffer should be 1-4KiB. Use 512 bytes (-10 already read) to avoid potentially
            # depleting the buffer and triggering another IO call, if possible.
            # If extra fields were present and >512 bytes, so be it.
            buffer = fobj.read(502)
    except OSError:
        return None

    filename = ''
    if flags & 0b0_1000:  # FNAME
        fname, buffer = buffer.split(b'\x00', 1)
        filename = fname.decode('latin-1')

    comment = ''
    if flags & 0b1_0000:  # FCOMMENT
        # If the comment extends beyond the buffer, split will return one entry.
        # *_ accounts for this by setting `_ = []`.
        cmnt, *_ = buffer.split(b'\x00', 1)
        comment = cmnt.decode('latin-1')

    return ctx.Gzip(timestamp=timestamp, filename=filename, comment=comment)


def tree_contains(tree: FileTree, relpath: str) -> bool:
    """Return whether a POSIX path, relative to ``tree``, names a file or folder in it.

    The path is split on ``/`` by hand rather than parsed as a path object. Two
    reasons, both found through the schema's ``exists()`` rules:

    * A leading ``/`` means the tree root. Every ``path`` in the context starts with
      one (``/sub-01/anat/sub-01_T1w.nii.gz``), and ``rules.checks.general.DuplicateFiles``
      passes such a path to ``exists(..., "dataset")``. Parsed as a path object it is
      absolute, never matched, and the rule could not fire.
    * A value that is not a path, such as a ``bids::`` URI given to the ``"subject"``
      rule, is simply not found. Parsed as a path object it raised
      ``ValueError: Protocol not known: 'bids'``.

    Empty and ``.`` segments are skipped, so ``sub-01//anat`` and ``./README`` work;
    ``..`` is never a child name, so it is never found.
    """
    node = tree
    for part in relpath.split('/'):
        if part in ('', '.'):
            continue
        child = node.children.get(part)
        if child is None:
            return False
        node = child
    return node is not tree


class Subjects:
    """Collections of subjects in the dataset."""

    def __init__(self, tree: FileTree):
        self._tree = tree

    @cached_property
    def sub_dirs(self) -> list[str]:
        """Subjects as determined by sub-* directories."""
        return [
            child.name
            for child in self._tree.children.values()
            if child.is_dir and child.name.startswith('sub-')
        ]

    @property
    def participant_id(self) -> list[str] | None:
        """The participant_id column of participants.tsv."""
        if 'participants.tsv' not in self._tree.children:
            return None

        return self._get_participant_id(self._tree.children['participants.tsv'])

    @cached_property
    def phenotype(self) -> list[str] | None:
        """The union of participant_id columns in phenotype files."""
        if 'phenotype' not in self._tree.children:
            return None

        subjects: set[str] = set()
        for phenotype_file in self._tree.children['phenotype'].children.values():
            if phenotype_file.name.endswith('.tsv'):
                subjects.update(self._get_participant_id(phenotype_file) or [])

        return sorted(subjects)

    @staticmethod
    def _get_participant_id(phenotype_file: FileTree) -> list[str] | None:
        try:
            columns = load_tsv(phenotype_file)
        except (ValidationError, OSError, UnicodeDecodeError):
            return None  # reported when the table itself is checked
        if 'participant_id' not in columns:
            return None
        return list(columns['participant_id'])


@attrs.define
class Dataset:
    """A dataset object that loads properties on first access."""

    tree: FileTree
    schema: Namespace
    ignored: list[str] = attrs.field(factory=list)
    subjects: Subjects = attrs.field(init=False)
    # "location:key" of every sidecar value already checked against the schema, so a
    # value in a shared sidecar is reported once, not once per data file using it. The
    # reference validator keeps the same set on its dataset (``sidecarKeyValidated``).
    checked_sidecar_values: set[str] = attrs.field(factory=set, init=False)

    def __attrs_post_init__(self) -> None:
        self.subjects = Subjects(self.tree)

    @cached_property
    def dataset_description(self) -> FileContents:
        """Contents of '/dataset_description.json', with ``DatasetType`` filled in.

        A missing or unreadable file gives an empty description (the integrity checks
        report it). ``DatasetType`` defaults as in the reference validator:
        ``derivative`` when ``GeneratedBy`` is present, otherwise ``raw``. Without the
        default, every rule selecting ``DatasetType == "raw"`` skips the many datasets
        that leave the field out.
        """
        description = FileContents()
        node = self.tree.children.get('dataset_description.json')
        if node is not None:
            try:
                description = FileContents(load_json(node))  # a copy: load_json is cached
            except (ValidationError, OSError):
                pass
        if not description.get('DatasetType'):
            description['DatasetType'] = 'derivative' if 'GeneratedBy' in description else 'raw'
        return description

    @cached_property
    def modalities(self) -> list[str]:
        """List of modalities found in the dataset."""
        result = {datatype_to_modality(datatype, self.schema) for datatype in self.datatypes}
        return [modality for modality in result if modality is not None]

    @cached_property
    def datatypes(self) -> list[str]:
        """List of datatypes found in the dataset."""
        return list(find_datatypes(self.tree, self.schema.objects.datatypes))


def find_datatypes(
    tree: FileTree, datatypes: Namespace, result: set[str] | None = None, max_depth: int = 2
) -> set[str]:
    """Recursively work through tree to find datatypes."""
    if result is None:
        result = set()

    for child_name, child_obj in tree.children.items():
        if not child_obj.is_dir:
            continue

        # ``.keys()``, not the Namespace itself: ``".git" in namespace`` reads the dot as a
        # path separator and inserts an empty key into the (cached, shared) schema.
        if child_name in datatypes.keys():  # noqa: SIM118
            result.add(child_name)
        elif max_depth == 0:
            continue
        else:
            result = find_datatypes(child_obj, datatypes, result, max_depth=max_depth - 1)

    return result


@attrs.define
class Association:
    """Generic association, exposing the associated file's path."""

    _file: FileTree

    @property
    def path(self) -> str:
        """Dataset-relative path of the associated file."""
        return self._file.relative_path


def load_file(file: FileTree, dataset: proto.Dataset) -> None:  # -> ctx.Context:
    """Load a full context for a given file."""
    # associations = load_associations(file, dataset)


def load_associations(file: FileTree, dataset: proto.Dataset) -> None:  # -> ctx.Associations:
    """Load all associations for a given file."""
    # If something fails, return None.
    # Uses walk back algorithm
    # https://bids-validator.readthedocs.io/en/latest/validation-model/inheritance-principle.html
    # Stops on first success


def load_events(file: FileTree) -> None:  # -> ctx.Events:
    """Load events.tsv file."""


def load_sidecar(file: FileTree) -> dict[str, t.Any]:
    """Load sidecar metadata, using the inheritance principle.

    For one file on its own. A validation reads :attr:`Context.sidecar` instead, which
    reuses the chain of JSON files the context found once.
    """
    return _merge_sidecars(_sidecar_files(file))


def _sidecar_files(file: FileTree) -> tuple[FileTree, ...]:
    """Return the JSON files ``file`` inherits metadata from, nearest first.

    Uses the walk back algorithm:
    https://bids-validator.readthedocs.io/en/latest/validation-model/inheritance-principle.html
    Raises :class:`ValidationError` (``MULTIPLE_INHERITABLE_FILES``) when one level has
    several equally good candidates.
    """
    # walk_back yields lists only when it searches for several targets; not here.
    return tuple(json for json in walk_back(file, inherit=True) if isinstance(json, FileTree))


def _merge_sidecars(jsons: t.Iterable[FileTree]) -> dict[str, t.Any]:
    """Merge JSON files given nearest first: the nearest file's value of a key wins."""
    metadata: dict[str, t.Any] = {}
    for json in jsons:
        try:
            metadata = load_json(json) | metadata
        except ValidationError:
            # A sidecar that does not parse is reported when it is checked itself;
            # the others still apply, as in the reference validator.
            continue
    return metadata


def walk_back(
    source: FileTree,
    inherit: bool,
    target_extensions: tuple[str, ...] = ('.json',),
    target_suffix: str | None = None,
    target_entities: tuple[str, ...] = (),
) -> Generator[FileTree] | Generator[list[FileTree]]:
    """Walk up the file tree to find associated files."""
    for file_group in _walk_back(
        source, inherit, target_extensions, target_suffix, target_entities
    ):
        if target_entities:
            yield file_group
        elif len(file_group) == 1:
            yield file_group[0]
        elif file_group:
            # Several candidates at one level: one carrying every entity of the source
            # wins, as in the reference validator. Only without one is it ambiguous.
            source_entities = FileParts.from_file(source).entities
            exact = [
                f
                for f in file_group
                if all(
                    FileParts.from_file(f).entities.get(key) == value
                    for key, value in source_entities.items()
                )
            ]
            if exact:
                yield exact[0]
                continue
            paths = sorted(f.relative_path for f in file_group)
            raise ValidationError(
                'MULTIPLE_INHERITABLE_FILES',
                'Candidate files: ' + ', '.join(paths),
                location=paths[0],
            )


def _walk_back(
    source: FileTree,
    inherit: bool,
    target_extensions: tuple[str, ...],
    target_suffix: str | None,
    target_entities: tuple[str, ...],
) -> Generator[list[FileTree]]:
    file_parts = FileParts.from_file(source)

    if target_suffix is None:
        target_suffix = file_parts.suffix

    tree = source.parent
    while tree:
        matches = []
        for child in tree.children.values():
            if child.is_dir:
                continue
            parts = FileParts.from_file(child)
            if parts.extension not in target_extensions:
                continue
            if parts.suffix != target_suffix:
                continue
            if all(
                key in target_entities or file_parts.entities.get(key) == value
                for key, value in parts.entities.items()
            ):
                matches.append(child)

        yield matches
        if not inherit:
            break
        tree = tree.parent


@attrs.define
class FileParts:
    """BIDS-relevant components of a file path."""

    path: str
    stem: str
    entities: dict[str, str | None]
    datatype: str | None
    suffix: str | None
    extension: str | None

    @classmethod
    def from_file(cls, file: FileTree, schema: Namespace | None = None) -> t.Self:
        """Parse file parts from FileTree object."""
        stem, _, extension = file.name.partition('.')

        if extension:
            extension = f'.{extension}'
        if file.is_dir:
            extension = f'{extension}/'

        datatype = None
        if (
            file.parent
            and schema
            and any(file.parent.name == dtype.value for dtype in schema.objects.datatypes.values())
        ):
            datatype = file.parent.name

        *entity_strings, suffix = stem.split('_')
        entities = {
            key: vals[0] if vals else None
            for key, *vals in (string.split('-', 1) for string in entity_strings)
        }

        return cls(
            path=f'/{file.relative_path}',
            stem=stem,
            entities=entities,
            datatype=datatype,
            suffix=suffix,
            extension=extension,
        )


@attrs.define
class Context:
    """A context object that creates context for file on access."""

    file: FileTree
    dataset: Dataset
    subject: ctx.Subject | None
    file_parts: FileParts = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        self.file_parts = FileParts.from_file(self.file, self.schema)

    @property
    def schema(self) -> Namespace:
        """The BIDS specification schema."""
        return self.dataset.schema

    @property
    def path(self) -> str:
        """Path of the current file."""
        return self.file_parts.path

    @property
    def entities(self) -> dict[str, str | None]:
        """Entities parsed from the current filename."""
        return self.file_parts.entities

    @property
    def datatype(self) -> str | None:
        """Datatype of current file, for examples, anat."""
        return self.file_parts.datatype

    @property
    def suffix(self) -> str | None:
        """Suffix of current file."""
        return self.file_parts.suffix

    @property
    def extension(self) -> str | None:
        """Extension of current file including initial dot."""
        return self.file_parts.extension

    @property
    def modality(self) -> str | None:
        """Modality of current file, for examples, MRI."""
        if (datatype := self.file_parts.datatype) is not None:
            return datatype_to_modality(datatype, self.schema)
        return None

    @property
    def size(self) -> int:
        """Length of the current file in bytes."""
        return self.file.path_obj.stat().st_size

    @property
    def associations(self) -> ctx.Associations:
        """Associated files, indexed by suffix, selected according to the inheritance principle."""
        return ctx.Associations()

    @cached_property
    def columns(self) -> FileContents | None:
        """TSV columns, indexed by column header, values are arrays with column contents.

        A table that cannot be read gives empty columns; the integrity checks report
        why (they call :meth:`read_columns`, which raises).
        """
        try:
            return self.read_columns()
        except (ValidationError, OSError, UnicodeDecodeError):
            return FileContents()

    def read_columns(self) -> FileContents | None:
        """Read this file's table, raising :class:`ValidationError` if it is malformed.

        The first :data:`TSV_MAX_ROWS` rows are read. A ``.tsv.gz`` has no header row:
        its column names come from the sidecar's ``Columns``, and without them there is
        nothing to read. A ``_motion.tsv`` has no header row either (its columns are
        named by the ``_channels.tsv`` association, not built yet). None for a file
        that is not a table.
        """
        if self.extension == '.tsv':
            if self.suffix == 'motion':
                return FileContents()
            return load_tsv(self.file, max_rows=TSV_MAX_ROWS)
        if self.extension == '.tsv.gz':
            headers = self.sidecar.get('Columns')
            if not isinstance(headers, list) or not headers or self.size == 0:
                return FileContents()
            return load_tsv_gz(self.file, tuple(str(h) for h in headers), max_rows=TSV_MAX_ROWS)
        return None

    @cached_property
    def json(self) -> FileContents | None:
        """Contents of the current JSON file; empty when it cannot be read."""
        if self.file_parts.extension == '.json':
            try:
                return load_json(self.file)
            except (ValidationError, OSError):
                return FileContents()

        return None

    @cached_property
    def gzip(self) -> ctx.Gzip | None:
        """Parsed contents of gzip header."""
        if self.path.endswith('.gz'):
            return load_gzip_header(self.file)
        return None

    @cached_property
    def nifti_header(self) -> ctx.NiftiHeader | None:
        """Parsed contents of NIfTI header referenced elsewhere in schema.

        None when the header cannot be read; the integrity checks report it.
        """
        if self.extension in ('.nii', '.nii.gz'):
            try:
                return load_nifti_header(self.file)
            except NIFTI_LOAD_ERRORS:
                return None
        return None

    @property
    def ome(self) -> None:
        """Parsed contents of OME-XML header, which may be found in OME-TIFF or OME-ZARR files."""

    @property
    def tiff(self) -> None:
        """TIFF file format metadata."""

    @cached_property
    def sidecar_files(self) -> tuple[FileTree, ...]:
        """The JSON files this file inherits metadata from, nearest first.

        Found once per file, because walking up the tree is the costly part, and read
        by :attr:`sidecar`, :attr:`sidecar_origins`, the integrity checks (which report
        an ambiguous chain) and the inheritance checks (which report a deeper file
        changing a value). Kept only as long as this context.

        A JSON file has none: it is a sidecar, it does not have one (as in the
        reference validator). Raises :class:`ValidationError`
        (``MULTIPLE_INHERITABLE_FILES``) when one level has several equally good
        candidates; an error is not cached, so every reader gets it.
        """
        if self.extension == '.json':
            return ()
        return _sidecar_files(self.file)

    @cached_property
    def sidecar_origins(self) -> dict[str, str]:
        """Map each key of :attr:`sidecar` to the dataset-relative path of its JSON file.

        A finding about a key's value belongs to the file that holds it, not to every
        data file inheriting it. An ambiguous chain gives no origins (its sidecar is
        empty too).
        """
        try:
            files = self.sidecar_files
        except ValidationError:
            return {}
        origins: dict[str, str] = {}
        for json in files:
            try:
                keys = load_json(json).keys()
            except ValidationError:
                continue
            for key in keys:
                origins.setdefault(key, json.relative_path)  # the nearest file wins
        return origins

    @cached_property
    def sidecar(self) -> FileContents:
        """Sidecar metadata constructed via the inheritance principle.

        As in the reference validator: a JSON file has no sidecar (it is one), so its
        sidecar is empty; a sidecar that cannot be read leaves the sidecar empty (the
        problem is reported on the JSON file itself); and ``RepetitionTime`` is
        rounded to milliseconds, so a header and a sidecar that differ only by float
        noise do not disagree.
        """
        try:
            sidecar = FileContents(_merge_sidecars(self.sidecar_files))
        except (ValidationError, OSError):
            return FileContents()
        repetition_time = sidecar.get('RepetitionTime')
        if isinstance(repetition_time, (int, float)) and not isinstance(repetition_time, bool):
            # JavaScript's Math.round (half up), not Python's round (half to even).
            sidecar['RepetitionTime'] = math.floor(repetition_time * 1000 + 0.5) / 1000
        return sidecar

    def exists(self, arg: str | list[str] | None, rule: str | None = 'dataset') -> int:
        """Count of files in an array that exist in the dataset. String is array with length 1."""
        if arg is None:
            return 0

        prefix = ''
        fileTree: FileTree = self.file.parent if rule == 'file' else self.dataset.tree  # type: ignore[assignment]

        if rule == 'stimuli':
            prefix = 'stimuli'
        elif rule == 'subject':
            if 'sub' not in self.entities:
                return 0
            prefix = f'sub-{self.entities["sub"]}'

        if isinstance(arg, str):
            arg = [arg]

        if rule == 'bids-uri':
            valid_uris = (uri for uri in arg if uri.startswith('bids:') and uri.count(':') == 2)
            uri_parts = [uri.split(':') for uri in valid_uris]

            # Find number of files in this dataset that exist
            # Once split these can be processed using dataset rule
            dataset_files = self.exists([part[2] for part in uri_parts if part[1] == ''])

            outside_files = [[part[1], part[2]] for part in uri_parts if part[1] != '']

            # Find number of files in other dataset that exist
            if outside_files:
                # Resolve dataset links relative to the dataset path
                dataset_links = getattr(self.dataset.dataset_description, 'DatasetLinks', {})
                links = {
                    key: (fileTree.path_obj / val).resolve() for key, val in dataset_links.items()
                }

                # For each uri with another dataset, generate the full path and sum the ones
                # that exist
                other_files = sum(
                    UPath(links[ds_name], relpath).exists()
                    for ds_name, relpath in outside_files
                    if ds_name in links
                )
            else:
                other_files = 0

            return dataset_files + other_files
        else:
            return sum(tree_contains(fileTree, f'{prefix}/{file}') for file in arg)


class Sessions:
    """Collections of sessions in subject."""

    def __init__(self, tree: FileTree):
        self._tree = tree

    @cached_property
    def ses_dirs(self) -> list[str]:
        """Sessions as determined by ses-* directories."""
        return [
            child.name
            for child in self._tree.children.values()
            if child.is_dir and child.name.startswith('ses-')
        ]

    @property
    def session_id(self) -> list[str] | None:
        """The session_id column of *_sessions.tsv."""
        for name, value in self._tree.children.items():
            if name.endswith('_sessions.tsv'):
                return self._get_session_id(value)
        return None

    @staticmethod
    def _get_session_id(phenotype_file: FileTree) -> list[str] | None:
        try:
            columns = load_tsv(phenotype_file)
        except (ValidationError, OSError, UnicodeDecodeError):
            return None  # reported when the table itself is checked
        if 'session_id' not in columns:
            return None
        return list(columns['session_id'])
