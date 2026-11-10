"""Whether each file can be read at all.

These are the checks the schema does not state as rules, because they come before any
rule can be read: a file that is empty, a JSON file that does not parse, a NIfTI
header that cannot be read, a table whose rows have the wrong number of cells, a
dataset with no ``dataset_description.json``. The reference validator raises them
from its file loaders (``src/files/*.ts``) and its ``emptyFile`` check.

The loaders are the context's own (:mod:`bids_validator.context`), so every file is
read once: these checks call the loader, and turn the error it raises into a
finding. When a load fails, the context gives the schema rules an empty value
instead, so a broken file is reported here once rather than as a failed check in
every rule that reads it.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..context import ValidationError, load_json
from ..issues import Issue, IssueDefinition, Severity

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from ..context import Context, Dataset
    from ..types.files import FileTree

# The names other modules are meant to import from this one.
__all__ = [
    'INVALID_GZIP',
    'JSON_NOT_AN_OBJECT',
    'LOADER_ERRORS',
    'LOADER_ERRORS_IN_SCHEMA',
    'MISSING_DATASET_DESCRIPTION',
    'MULTIPLE_INHERITABLE_FILES',
    'TSV_COLUMN_HEADER_DUPLICATE',
    'TSV_EMPTY_LINE',
    'TSV_EQUAL_ROWS',
    'dataset_integrity_issues',
    'integrity_issues',
]

# --- what this module reports --------------------------------------------
#
# Defined by the schema, in rules.errors, and read from it where they are reported:
#
#   EMPTY_FILE                rules.errors.EmptyFile
#   NIFTI_HEADER_UNREADABLE   rules.errors.NiftiHeaderUnreadable
#   JSON_INVALID              rules.errors.JsonInvalid           (raised by a loader)
#   INVALID_JSON_ENCODING     rules.errors.InvalidJsonEncoding   (raised by a loader)
#
# Defined only by the reference validator (bids-validator, src/issues/list.ts):

# No ``dataset_description.json`` at the root of the dataset.
MISSING_DATASET_DESCRIPTION = IssueDefinition(
    'MISSING_DATASET_DESCRIPTION',
    Severity.ERROR,
    'A dataset_description.json file is required in the root of the dataset',
)

# The context's loaders (``load_json``, ``load_tsv`` ... in context.py) raise these, as
# the ``code`` of a ``ValidationError``; ``_issues_from_loader`` turns them into findings:
# A JSON file that parses, but holds a list or a number instead of ``{...}``.
JSON_NOT_AN_OBJECT = IssueDefinition(
    'JSON_NOT_AN_OBJECT', Severity.ERROR, 'Parsed JSON file does not contain an object.'
)
# An empty line in a table that is not the last line.
TSV_EMPTY_LINE = IssueDefinition(
    'TSV_EMPTY_LINE', Severity.ERROR, 'An empty line was found in the TSV file.'
)
# A table row with more or fewer cells than the header has columns.
TSV_EQUAL_ROWS = IssueDefinition(
    'TSV_EQUAL_ROWS',
    Severity.ERROR,
    'All rows must have the same number of columns as there are headers.',
)
# Two columns of one table with the same name.
TSV_COLUMN_HEADER_DUPLICATE = IssueDefinition(
    'TSV_COLUMN_HEADER_DUPLICATE',
    Severity.ERROR,
    'Two elements in the first row of a TSV are the same. Each column header must be unique.',
)
# A ``.tsv.gz`` that does not decompress.
INVALID_GZIP = IssueDefinition(
    'INVALID_GZIP',
    Severity.ERROR,
    'The gzip file could not be decompressed. It may be corrupt or misnamed.',
)
# Two JSON files at one level that apply equally well to a file.
MULTIPLE_INHERITABLE_FILES = IssueDefinition(
    'MULTIPLE_INHERITABLE_FILES',
    Severity.ERROR,
    'Multiple files in a directory were found to be valid candidates for inheritance.',
)

# Every code a loader can raise, and where its definition is. Two are defined by the
# schema, under these entry names in rules.errors; the others are defined above. A test
# (tests/checks/test_codes.py) checks that every code raised in context.py is in one of the two.
LOADER_ERRORS_IN_SCHEMA = {
    'JSON_INVALID': 'JsonInvalid',
    'INVALID_JSON_ENCODING': 'InvalidJsonEncoding',
}
LOADER_ERRORS = {
    definition.code: definition
    for definition in (
        JSON_NOT_AN_OBJECT,
        TSV_EMPTY_LINE,
        TSV_EQUAL_ROWS,
        TSV_COLUMN_HEADER_DUPLICATE,
        INVALID_GZIP,
        MULTIPLE_INHERITABLE_FILES,
    )
}


def integrity_issues(context: Context) -> list[Issue]:
    """Return the findings for a file that cannot be read the way its type needs.

    An empty image is reported twice (empty, and no header), as the reference
    validator does. A file that inherits from two equally good sidecars is reported
    as ``MULTIPLE_INHERITABLE_FILES``.
    """
    issues: list[Issue] = []
    if _size(context.file) == 0:
        issues.append(
            _schema_error(context.schema, 'EmptyFile').make_issue(context.file.relative_path)
        )
    extension = context.extension
    if extension == '.json':
        issues += _issues_from_loader(context, lambda: load_json(context.file))
    elif extension in ('.nii', '.nii.gz') and context.nifti_header is None:
        definition = _schema_error(context.schema, 'NiftiHeaderUnreadable')
        issues.append(definition.make_issue(context.file.relative_path))
    elif extension in ('.tsv', '.tsv.gz'):
        issues += _issues_from_loader(context, context.read_columns)
    # Finding the JSON files it inherits from raises if one level is ambiguous.
    issues += _issues_from_loader(context, lambda: context.sidecar_files)
    return issues


def dataset_integrity_issues(dataset: Dataset) -> list[Issue]:
    """Return the findings about the dataset as a whole: a missing description."""
    if 'dataset_description.json' in dataset.tree.children:
        return []
    return [
        MISSING_DATASET_DESCRIPTION.make_issue(
            None, message='there is no dataset_description.json at the root of the dataset'
        )
    ]


def _issues_from_loader(context: Context, load: Callable[[], object]) -> list[Issue]:
    """Run a loader; turn the :class:`ValidationError` it raises into a finding.

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
        definition = _definition_of_loader_code(context.schema, error.code)
        return [
            definition.make_issue(error.location or context.file.relative_path, message=message)
        ]
    except (OSError, UnicodeDecodeError):
        return []
    return []


def _definition_of_loader_code(schema: Namespace, code: str) -> IssueDefinition:
    """Return the definition of a code a loader raised, from the schema or from here."""
    if code in LOADER_ERRORS_IN_SCHEMA:
        return _schema_error(schema, LOADER_ERRORS_IN_SCHEMA[code])
    return LOADER_ERRORS[code]


def _schema_error(schema: Namespace, name: str) -> IssueDefinition:
    """Return the definition the schema gives under ``rules.errors.<name>``."""
    return IssueDefinition.from_schema(schema['rules']['errors'][name])


def _size(node: FileTree) -> int:
    """Return the size of a file, or of a directory recording: the sum of its files.

    A recording folder whose files are all empty is an empty file, as in the reference.
    Hidden files (``.zattrs`` in an OME-Zarr folder) do not count: the walk never
    visits them.
    """
    if not node.is_dir:
        return node.path_obj.stat().st_size
    return sum(_size(child) for child in node.children.values() if not child.name.startswith('.'))
