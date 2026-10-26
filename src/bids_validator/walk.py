"""Which files and folders a validation visits.

Every check works on one :class:`~bids_validator.context.Context` at a time. This
module decides which ones exist: it walks the dataset and yields a context for every
file and every folder that is not ignored, in the reference validator's order and
with its rules (``src/schema/walk.ts``, ``src/files/ignore.ts`` and
``src/validators/bids.ts`` in bids-validator):

* **Ignored, never visited:** the folders the reference ignores at the top of the
  dataset (:data:`DEFAULT_IGNORES`), hidden files and folders at every level
  (:data:`PRUNED`), and whatever the dataset's ``.bidsignore`` lists. ``.bidsignore``
  itself is visited.
* **Visited as one unit:** a directory recording, such as a CTF ``.ds`` folder. Its
  name has entities, a suffix, and an extension the schema spells with a trailing
  ``/``; it is checked like a file, and its vendor-named contents are not walked. The
  schema also lists a bare ``/`` (``objects.extensions.Directory``), so any folder
  named like a file, ``sub-01_xyz``, counts as one too, as in the reference.
* **Visited, not walked into:** an opaque folder (``rules.directories`` marks
  ``docs`` and ``logs`` opaque, for example).
* **Visited, then walked into:** every other folder.
* **A raw dataset's** ``derivatives`` folders are skipped wherever they are: a
  derivative is a separate dataset with separate rules. To check one, validate its
  own root.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from bidsschematools.types.context import Subject

from .bidsignore import Ignore, IgnoreMany
from .context import Context, Dataset, FileParts, Sessions

if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from .bidsignore import HasMatch
    from .types.files import FileTree

__all__ = [
    'DEFAULT_IGNORES',
    'DERIVATIVES_DIR',
    'PRUNED',
    'build_ignore',
    'is_directory',
    'iter_contexts',
]

# The reference validator's default "ignore" group: folders at the TOP of the dataset
# that BIDS does not constrain (the leading "/" anchors each pattern at the root).
DEFAULT_IGNORES = ('/sourcedata/', '/derivatives/', '/code/', '/stimuli/', '/log/', '/doc/')

# The reference validator's default "prune" group: hidden files and folders at every
# level (.git, .DS_Store, .datalad ...). Its exception, .bidsignore, is handled by name.
PRUNED = ('.**',)
BIDSIGNORE = '.bidsignore'

DERIVATIVES_DIR = 'derivatives'

# Per-schema caches. Schema objects live for the process, so id() is stable.
_RECORDING_EXT_MEMO: dict[int, frozenset[str]] = {}


def iter_contexts(dataset: Dataset, ignore: HasMatch | None = None) -> Iterator[Context]:
    """Yield a context for every file and folder a validation should look at.

    Parameters
    ----------
    dataset : Dataset
        The dataset, which pairs the file tree with the schema.
    ignore : HasMatch, optional
        The ignore matcher; :func:`build_ignore` by default.

    Yields
    ------
    Context
        One per visited file or folder, depth first, files before folders as in the
        reference validator. A folder's context has ``context.file.is_dir`` true; use
        :func:`is_directory` to tell a plain folder from a directory recording.

    """
    if ignore is None:
        ignore = build_ignore(dataset.tree)
    raw = str(dataset.dataset_description.get('DatasetType')) == 'raw'
    yield from _walk(dataset.tree, dataset, ignore, raw, _opaque_names(dataset), subject=None)


def build_ignore(tree: FileTree) -> IgnoreMany:
    """Build the ignore matcher: the reference defaults plus the dataset's .bidsignore."""
    ignores = [Ignore(list(DEFAULT_IGNORES + PRUNED))]
    bidsignore = tree.children.get(BIDSIGNORE)
    if bidsignore is not None:
        ignores.append(Ignore.from_file(bidsignore))
    return IgnoreMany(ignores)


def is_directory(context: Context) -> bool:
    """Whether the context is a plain folder, as opposed to a file or a recording.

    A directory recording (``sub-01_task-x_meg.ds/``) is a folder on disk but a file
    to BIDS, so it is not a plain folder.
    """
    return context.file.is_dir and not _is_recording(context.file, context.schema)


def _walk(
    tree: FileTree,
    dataset: Dataset,
    ignore: HasMatch,
    raw: bool,
    opaque: frozenset[str],
    subject: Subject | None,
) -> Iterator[Context]:
    """Yield the contexts below ``tree``: its files first, then each folder and its contents.

    Each context carries the :class:`Subject` of the enclosing ``sub-*`` folder.
    """
    if subject is None and tree.name.startswith('sub-'):
        subject = Subject(Sessions(tree))

    children = list(tree.children.values())
    for child in children:
        if not child.is_dir and _visited(child, ignore):
            yield Context(child, dataset, subject)

    for child in children:
        if not child.is_dir or not _visited(child, ignore):
            continue
        if raw and child.name == DERIVATIVES_DIR:
            continue  # a separate dataset with separate rules
        yield Context(child, dataset, subject)
        if _is_recording(child, dataset.schema):
            continue  # one unit: its own name is checked, its contents are not
        if child.parent is dataset.tree and child.name in opaque:
            continue  # BIDS does not constrain what is inside
        yield from _walk(child, dataset, ignore, raw, opaque, subject)


def _visited(node: FileTree, ignore: HasMatch) -> bool:
    """Whether a file or folder is visited: not ignored, or the .bidsignore itself."""
    if node.relative_path == BIDSIGNORE:
        return True
    return not ignore.match(node.relative_path)


def _is_recording(node: FileTree, schema: Namespace) -> bool:
    """Whether a folder is a directory recording, by the reference validator's test.

    Its name must have at least one entity, a suffix, and an extension the schema
    lists with a trailing ``/`` (``.ds/``, ``.mefd/``, ``.ome.zarr/``, and ``/`` for a
    folder with no extension at all). A folder called ``old.ds`` with no entities is an
    ordinary folder.
    """
    if not node.is_dir:
        return False
    parts = FileParts.from_file(node)
    return bool(
        parts.entities and parts.suffix and parts.extension in _recording_extensions(schema)
    )


def _recording_extensions(schema: Namespace) -> frozenset[str]:
    """Return the schema's directory-recording extensions, with their trailing ``/``."""
    cached = _RECORDING_EXT_MEMO.get(id(schema))
    if cached is None:
        cached = frozenset(
            str(definition['value'])
            for definition in schema['objects']['extensions'].values()
            if str(definition.get('value', '')).endswith('/')
        )
        _RECORDING_EXT_MEMO[id(schema)] = cached
    return cached


def _opaque_names(dataset: Dataset) -> frozenset[str]:
    """Top-level folders the schema marks opaque for this kind of dataset."""
    kind = str(dataset.dataset_description.get('DatasetType'))
    rules = dataset.schema['rules']['directories'].get(kind, {})
    return frozenset(
        str(rules[key]['name'])
        for key in rules
        if rules[key].get('opaque') and 'name' in rules[key].keys()  # noqa: SIM118
    )
