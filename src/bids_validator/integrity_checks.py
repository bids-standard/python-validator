"""Check whether each file can be read at all.

These are the checks the schema does not state as rules, because they come before
any rule can be read: a file that is empty, a JSON file that does not parse, a NIfTI
header that cannot be read, a table whose rows have the wrong number of cells, a
dataset with no ``dataset_description.json``. The reference validator raises them
from its file loaders (``src/files/*.ts``) and its ``emptyFile`` check.

The loaders are the context's own (:mod:`bids_validator.context`), so every file is
read once: these checks ask the loader, and turn the error it raises into a finding.
When a load fails, the context gives the schema rules an empty value instead, so a
broken file is reported here once rather than as a failed check in every rule that
reads it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .context import ValidationError, load_json, load_sidecar
from .issues import Issue, coded_issue
from .walk import is_directory

if TYPE_CHECKING:
    from .context import Context, Dataset
    from .types.files import FileTree

__all__ = ['dataset_integrity_issues', 'integrity_issues']


def integrity_issues(context: Context) -> list[Issue]:
    """Return the findings for a file that cannot be read the way its type needs.

    Codes: ``EMPTY_FILE``; ``INVALID_JSON_ENCODING``, ``JSON_INVALID``,
    ``JSON_NOT_AN_OBJECT``; ``NIFTI_HEADER_UNREADABLE``; ``TSV_COLUMN_HEADER_DUPLICATE``,
    ``TSV_EMPTY_LINE``, ``TSV_EQUAL_ROWS``, ``INVALID_GZIP``;
    ``MULTIPLE_INHERITABLE_FILES``. An empty image is reported twice (empty, and no
    header), as the reference validator does.
    """
    if is_directory(context):
        return []
    issues: list[Issue] = []
    if _size(context.file) == 0:
        issues.append(coded_issue(context.schema, 'EMPTY_FILE', location=_location(context)))
    extension = context.extension
    if extension == '.json':
        issues += _load_errors(context, lambda: load_json(context.file))
    elif extension in ('.nii', '.nii.gz') and context.nifti_header is None:
        issues.append(
            coded_issue(context.schema, 'NIFTI_HEADER_UNREADABLE', location=_location(context))
        )
    elif extension in ('.tsv', '.tsv.gz'):
        issues += _load_errors(context, context.read_columns)
    if extension != '.json':
        issues += _load_errors(context, lambda: load_sidecar(context.file))
    return issues


def dataset_integrity_issues(dataset: Dataset) -> list[Issue]:
    """Return the findings about the dataset as a whole: a missing description."""
    if 'dataset_description.json' in dataset.tree.children:
        return []
    return [
        coded_issue(
            dataset.schema,
            'MISSING_DATASET_DESCRIPTION',
            location=None,
            message='there is no dataset_description.json at the root of the dataset',
        )
    ]


def _load_errors(context: Context, load: Callable[[], object]) -> list[Issue]:
    """Run a loader; turn the coded :class:`ValidationError` it raises into a finding.

    Only coded errors are findings. A file that is not valid UTF-8 text, for example,
    raises ``UnicodeDecodeError``, which the reference validator does not report
    either; the rules that read the file then see an empty value.
    """
    try:
        load()
    except ValidationError as error:
        message = error.message
        if error.line is not None:
            message = f'line {error.line}' + (f': {message}' if message else '')
        return [
            coded_issue(
                context.schema,
                error.code,
                location=error.location or _location(context),
                message=message,
            )
        ]
    except (OSError, UnicodeDecodeError):
        return []
    return []


def _size(node: FileTree) -> int:
    """Return the size of a file, or of a directory recording: the sum of its files.

    A recording folder whose files are all empty is an empty file, as in the reference.
    Hidden files (``.zattrs`` in an OME-Zarr folder) do not count: the walk never
    visits them.
    """
    if not node.is_dir:
        return node.path_obj.stat().st_size
    return sum(_size(child) for child in node.children.values() if not child.name.startswith('.'))


def _location(context: Context) -> str:
    """Return the file's dataset-relative path, the form every finding uses."""
    return context.file.relative_path
