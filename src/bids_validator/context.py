"""Classes and functions for populating a validation context."""

from __future__ import annotations

import itertools
import json
from functools import cache

import attrs
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


@cache
def load_tsv(file: FileTree, *, max_rows=0) -> Namespace:
    """Load TSV contents into a Namespace."""
    with open(file) as fobj:
        if max_rows > 0:
            fobj = itertools.islice(fobj, max_rows)
        contents = (line.rstrip('\r\n').split('\t') for line in fobj)
        # Extract headers then transpose rows to columns
        return Namespace(zip(next(contents), zip(*contents)))


@cache
def load_json(file: FileTree) -> dict[str]:
    """Load JSON file contents."""
    with open(file) as fobj:
        return json.load(fobj)


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

        subjects = set()
        for phenotype_file in self._tree.children['phenotype'].children:
            if phenotype_file.name.endswith('.tsv'):
                subjects.update(self._get_participant_id(phenotype_file))

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
        result = set()

        modalities = self.schema.rules.modalities
        for datatype in self.datatypes:
            for mod_name, mod_dtypes in modalities.items():
                if datatype in mod_dtypes.datatypes:
                    result.add(mod_name)

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


def walk_back(
    source: FileTree,
    inherit: bool,
    target_extensions: tuple[str, ...] = ('.json',),
    target_suffix: str | None = None,
    target_entities: tuple[str, ...] = (),
) -> Generator[FileTree] | Generator[list[FileTree, ...]]:
    """Walk up the file tree to find associated files."""
    for file_group in _walk_back(
        source, inherit, target_extensions, target_suffix, target_entities
    ):
        if target_entities:
            yield file_group
        elif len(file_group) == 1:
            yield file_group[0]
        else:
            raise ValidationError('Multiple matching files.')


def _walk_back(
    source: FileTree,
    inherit: bool,
    target_extensions: tuple[str, ...],
    target_suffix: str | None,
    target_entities: tuple[str, ...],
) -> Generator[list[FileTree, ...]]:
    file_parts = FileParts.from_file(source.relative_path)

    if target_suffix is None:
        target_suffix = file_parts.suffix

    tree = source.parent
    while tree:
        matches = []
        for child in tree.children:
            if child.is_dir:
                continue
            parts = FileParts.from_file(child.relative_path)
            if parts.extension != target_extensions:
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
