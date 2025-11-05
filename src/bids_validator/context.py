"""Classes and functions for populating a validation context."""

from __future__ import annotations

import gzip
import itertools
from functools import cache

import attrs
import orjson
from bidsschematools.types import Namespace
from bidsschematools.types import context as ctx
from upath import UPath

from .types import _typings as t
from .types.files import FileTree

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator

    from bidsschematools.types import protocols as proto

    # pyright does not treat cached_property like property
    cached_property = property
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
    """TODO: Add issue structure."""


_DATATYPE_MAP: dict[str, str] = {}


def datatype_to_modality(datatype: str, schema: Namespace) -> str:
    """Generate a global map for datatype to modality."""
    global _DATATYPE_MAP
    if not _DATATYPE_MAP:
        for mod_name, mod_dtypes in schema.rules.modalities.items():
            _DATATYPE_MAP |= dict.fromkeys(mod_dtypes['datatypes'], mod_name)
    return _DATATYPE_MAP[datatype]


@cache
def load_tsv(file: FileTree, *, max_rows=0) -> Namespace:
    """Load TSV contents into a Namespace."""
    fobj: t.Iterable[str]
    with file.path_obj.open() as fobj:
        if max_rows > 0:
            fobj = itertools.islice(fobj, max_rows)
        contents = (line.rstrip('\r\n').split('\t') for line in fobj)
        # Extract headers then transpose rows to columns
        return Namespace(zip(next(contents), zip(*contents, strict=False), strict=False))


@cache
def load_tsv_gz(file: FileTree, headers: tuple[str], *, max_rows=0) -> Namespace:
    """Load TSVGZ contents into a Namespace."""
    with file.path_obj.open('rb') as fobj:
        gzobj: t.Iterable[bytes] = gzip.GzipFile(fileobj=fobj, mode='r')
        if max_rows > 0:
            gzobj = itertools.islice(gzobj, max_rows)
        contents = (line.decode().rstrip('\r\n').split('\t') for line in gzobj)
        return Namespace(zip(headers, zip(*contents, strict=False), strict=False))


@cache
def load_json(file: FileTree) -> dict[str, t.Any]:
    """Load JSON file contents."""
    return orjson.loads(file.path_obj.read_bytes())


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
        columns = load_tsv(phenotype_file)
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

    def __attrs_post_init__(self):
        self.subjects = Subjects(self.tree)

    @cached_property
    def dataset_description(self) -> Namespace:
        """Contents of '/dataset_description.json'."""
        return Namespace.from_json(
            UPath(self.tree.children['dataset_description.json']).read_text()
        )

    @cached_property
    def modalities(self) -> list[str]:
        """List of modalities found in the dataset."""
        result = {datatype_to_modality(datatype, self.schema) for datatype in self.datatypes}
        return list(result)

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

        if child_name in datatypes.keys():
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
    def path(self):
        """Dataset-relative path of the associated file."""
        return self._file.relative_path


def load_file(file: FileTree, dataset: proto.Dataset) -> ctx.Context:
    """Load a full context for a given file."""
    associations = load_associations(file, dataset)
    _ = associations


def load_associations(file: FileTree, dataset: proto.Dataset) -> ctx.Associations:
    """Load all associations for a given file."""
    # If something fails, return None.
    # Uses walk back algorithm
    # https://bids-validator.readthedocs.io/en/latest/validation-model/inheritance-principle.html
    # Stops on first success


def load_events(file: FileTree) -> ctx.Events:
    """Load events.tsv file."""


def load_sidecar(file: FileTree) -> dict[str, t.Any]:
    """Load sidecar metadata, using the inheritance principle."""
    # Uses walk back algorithm
    # https://bids-validator.readthedocs.io/en/latest/validation-model/inheritance-principle.html
    # Accumulates all sidecars
    metadata: dict[str, t.Any] = {}

    for json in walk_back(file, inherit=True):
        metadata = load_json(json) | metadata

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
            raise ValidationError(f'Multiple matching files: {file_group}')


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
        if file.parent and schema:
            if any(file.parent.name == dtype.value for dtype in schema.objects.datatypes.values()):
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

    def __attrs_post_init__(self):
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

    @property
    def columns(self) -> Namespace | None:
        """TSV columns, indexed by column header, values are arrays with column contents."""
        if self.extension == '.tsv':
            return load_tsv(self.file)
        elif self.extension == '.tsv.gz':
            columns = tuple(self.sidecar.Columns) if self.sidecar else ()
            return load_tsv_gz(self.file, columns)
        return None

    @property
    def json(self) -> Namespace | None:
        """Contents of the current JSON file."""
        if self.file_parts.extension == '.json':
            return Namespace.build(load_json(self.file))

        return None

    @property
    def gzip(self) -> None:
        """Parsed contents of gzip header."""
        pass

    @property
    def nifti_header(self) -> None:
        """Parsed contents of NIfTI header referenced elsewhere in schema."""
        pass

    @property
    def ome(self) -> None:
        """Parsed contents of OME-XML header, which may be found in OME-TIFF or OME-ZARR files."""
        pass

    @property
    def tiff(self) -> None:
        """TIFF file format metadata."""
        pass

    @property
    def sidecar(self) -> Namespace | None:
        """Sidecar metadata constructed via the inheritance principle."""
        sidecar = load_sidecar(self.file) or {}

        return Namespace.build(sidecar)


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
        else:
            return None

    @staticmethod
    def _get_session_id(phenotype_file: FileTree) -> list[str] | None:
        columns = load_tsv(phenotype_file)
        if 'session_id' not in columns:
            return None
        return list(columns['session_id'])
