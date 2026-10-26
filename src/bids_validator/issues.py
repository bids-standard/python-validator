"""Typed validation findings for the BIDS validator.

Every problem the validator reports is an :class:`Issue`: a small, typed record
with a stable ``code``, a :class:`Severity`, the ``location`` of the offending
file, and a human-readable ``message``. Findings are gathered in a
:class:`DatasetIssues` container.

The field set is intentionally minimal and aligned to the reference (Deno)
``bids-validator`` issue shape, so structured output stays interchangeable. These
are pure-data ``attrs`` models with no I/O, ready to serialise to JSON or drive a
report. Richer fields (rule provenance, machine-actionable fixes) can be added
later without changing this core shape.

A finding's code, level and default message come from one of two places, and every
check builds its findings through one of two functions:

* The schema defines some issues itself: every rule in ``rules.checks`` carries an
  ``issue`` block, some field requirements do, and ``rules.errors`` lists general
  ones (``EMPTY_FILE``, ``JSON_INVALID`` ...). :func:`schema_issue` builds a finding
  from such a block.
* The other codes are defined only by the reference validator
  (``src/issues/list.ts`` in bids-validator). :data:`REFERENCE_CODES` mirrors them.
  :func:`coded_issue` builds a finding from a code, preferring the schema's
  ``rules.errors`` definition when the schema has one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from enum import Enum
from typing import Any

import attrs


class Severity(str, Enum):
    """How serious a finding is.

    Ordered from low to high attention: ``WARNING`` then ``ERROR``. Subclassing
    ``str`` keeps the values JSON-friendly, so a member serialises directly to
    ``'warning'`` or ``'error'``.
    """

    WARNING = 'warning'
    ERROR = 'error'

    @classmethod
    def from_level(cls, level: str) -> Severity:
        """Return the severity for a schema issue ``level``.

        The schema writes ``level: warning`` or ``level: error`` on every issue it
        defines (``rules.errors``, ``rules.checks``). Anything other than ``warning``
        is treated as an error, so an unexpected value is never silently downgraded.
        """
        return cls.WARNING if level == 'warning' else cls.ERROR


@attrs.define(kw_only=True)
class Issue:
    """A single validation finding.

    Attributes
    ----------
    code
        Stable issue identifier, aligned to the reference validator catalog (for
        example ``'FILENAME_MISMATCH'``).
    severity
        How serious the finding is. Defaults to :attr:`Severity.ERROR`.
    location
        Dataset-relative path of the offending file, when applicable.
    message
        Human-readable description of the finding.
    sub_code
        Optional finer category within ``code`` (for example an entity name).
    rule
        Dotted path of the schema rule that produced the finding, for example
        ``rules.files.raw.anat.nonparametric``.

    """

    code: str
    severity: Severity = Severity.ERROR
    location: str | None = None
    message: str | None = None
    sub_code: str | None = None
    rule: str | None = None


@attrs.define
class DatasetIssues:
    """An ordered, typed collection of findings.

    A thin wrapper over a list, so a report has a stable container that is easy to
    extend (filtering, severity rollup) without changing the call sites that build
    it.

    Attributes
    ----------
    issues
        The findings, in insertion order.

    """

    issues: list[Issue] = attrs.field(factory=list)

    def add(self, issue: Issue) -> None:
        """Append a single finding."""
        self.issues.append(issue)

    def extend(self, issues: Iterable[Issue]) -> None:
        """Append several findings."""
        self.issues.extend(issues)

    def by_severity(self, severity: Severity) -> list[Issue]:
        """Return the findings at exactly one severity, in insertion order."""
        return [issue for issue in self.issues if issue.severity is severity]

    @property
    def has_errors(self) -> bool:
        """Whether any finding is an error (used to drive a non-zero exit code)."""
        return any(issue.severity is Severity.ERROR for issue in self.issues)

    def __iter__(self) -> Iterator[Issue]:
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)


# Codes the BIDS schema does not define, with the severity and the reason the reference
# validator gives them (bids-validator ``src/issues/list.ts``). A code the schema does
# define in ``rules.errors`` is listed too, as the fallback for an older schema.
_ERROR, _WARNING = Severity.ERROR, Severity.WARNING
REFERENCE_CODES: dict[str, tuple[Severity, str]] = {
    # Names and places (filename_checks)
    'NOT_INCLUDED': (_ERROR, 'Files with such naming scheme are not part of BIDS specification.'),
    'ENTITY_WITH_NO_LABEL': (_ERROR, 'Found an entity with no label.'),
    'INVALID_ENTITY_LABEL': (
        _ERROR,
        "entity label doesn't match format found for files with this suffix",
    ),
    'MISSING_REQUIRED_ENTITY': (_ERROR, 'Missing required entity for files with this suffix.'),
    'ENTITY_NOT_IN_RULE': (
        _ERROR,
        'Entity not listed as required or optional for files with this suffix',
    ),
    'DATATYPE_MISMATCH': (
        _ERROR,
        'The datatype directory does not match datatype of found suffix and extension',
    ),
    'MISSING_DATATYPE': (_ERROR, 'The file is not located in a datatype directory.'),
    'EXTENSION_MISMATCH': (
        _ERROR,
        'Extension used by file does not match allowed extensions for its suffix',
    ),
    'INVALID_LOCATION': (
        _ERROR,
        'The file has a valid name, but is located in an invalid directory.',
    ),
    'FILENAME_MISMATCH': (
        _ERROR,
        (
            'The filename is not formatted correctly. This could result from entity '
            'duplication or reordering.'
        ),
    ),
    'ALL_FILENAME_RULES_HAVE_ISSUES': (
        _ERROR,
        (
            'Multiple filename rules were found as potential matches. All of them had at '
            'least one issue during filename validation.'
        ),
    ),
    'CASE_COLLISION': (
        _ERROR,
        'Files with the same name but different casing have been found.',
    ),
    # Reading files (integrity_checks)
    'MISSING_DATASET_DESCRIPTION': (
        _ERROR,
        'A dataset_description.json file is required in the root of the dataset',
    ),
    'EMPTY_FILE': (_ERROR, 'Empty files not allowed.'),
    'JSON_INVALID': (_ERROR, 'Not a valid JSON file.'),
    'INVALID_JSON_ENCODING': (_ERROR, 'JSON files must be valid UTF-8 encoded text.'),
    'JSON_NOT_AN_OBJECT': (_ERROR, 'Parsed JSON file does not contain an object.'),
    'NIFTI_HEADER_UNREADABLE': (
        _ERROR,
        (
            'We were unable to parse header data from this NIfTI file. Please ensure it is '
            'not corrupted or mislabeled.'
        ),
    ),
    'TSV_EMPTY_LINE': (_ERROR, 'An empty line was found in the TSV file.'),
    'TSV_EQUAL_ROWS': (
        _ERROR,
        'All rows must have the same number of columns as there are headers.',
    ),
    'TSV_COLUMN_HEADER_DUPLICATE': (
        _ERROR,
        'Two elements in the first row of a TSV are the same. Each column header must be unique.',
    ),
    'INVALID_GZIP': (
        _ERROR,
        'The gzip file could not be decompressed. It may be corrupt or misnamed.',
    ),
    'MULTIPLE_INHERITABLE_FILES': (
        _ERROR,
        'Multiple files in a directory were found to be valid candidates for inheritance.',
    ),
    # Schema rules (rule_checks, field_checks, table_checks)
    'CHECK_ERROR': (
        _ERROR,
        'generic place holder for errors from failed `checks` evaluated from schema.',
    ),
    'SIDECAR_KEY_REQUIRED': (
        _ERROR,
        "A data file's JSON sidecar is missing a key listed as required.",
    ),
    'SIDECAR_KEY_RECOMMENDED': (
        _WARNING,
        "A data file's JSON sidecar is missing a key listed as recommended.",
    ),
    'JSON_KEY_REQUIRED': (_ERROR, 'A JSON file is missing a key listed as required.'),
    'JSON_KEY_RECOMMENDED': (_WARNING, 'A JSON file is missing a key listed as recommended.'),
    'JSON_SCHEMA_VALIDATION_ERROR': (
        _ERROR,
        'Invalid JSON sidecar file. The sidecar is not formatted according the schema.',
    ),
    'SIDECAR_FIELD_OVERRIDE': (
        _WARNING,
        'Sidecar files should not override values assigned at a higher level.',
    ),
    'TSV_COLUMN_MISSING': (_ERROR, 'A required column is missing'),
    'TSV_COLUMN_ORDER_INCORRECT': (_ERROR, 'Some TSV columns are in the incorrect order'),
    'TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED': (
        _ERROR,
        'A TSV file has extra columns which are not allowed for its file type',
    ),
    'TSV_ADDITIONAL_COLUMNS_MUST_DEFINE': (
        _ERROR,
        'Additional TSV columns must be defined in the associated JSON sidecar for this file type',
    ),
    'TSV_ADDITIONAL_COLUMNS_UNDEFINED': (
        _WARNING,
        'A TSV file has extra columns which are not defined in its associated JSON sidecar',
    ),
    'TSV_COLUMN_TYPE_REDEFINED': (
        _WARNING,
        (
            'A column required in a TSV file has been redefined in a sidecar file. This '
            'redefinition is being ignored.'
        ),
    ),
    'TSV_VALUE_INCORRECT_TYPE': (
        _ERROR,
        (
            'A value in a column did not match the acceptable type for that column headers '
            'specified format.'
        ),
    ),
    'TSV_PSEUDO_AGE_DEPRECATED': (
        _WARNING,
        'Use of the value "89+" in column "age" is deprecated. Use 89 for all ages 89 and over.',
    ),
    'TSV_INDEX_VALUE_NOT_UNIQUE': (
        _ERROR,
        (
            'An index column(s) was specified for the tsv file and not all of the values for '
            'it are unique.'
        ),
    ),
}

# Per-schema index of ``rules.errors`` by code. Schema objects live for the process.
_SCHEMA_ERRORS_MEMO: dict[int, dict[str, Mapping[str, Any]]] = {}


def schema_issue(
    definition: Mapping[str, Any],
    *,
    location: str | None,
    severity: Severity | None = None,
    message: str | None = None,
    sub_code: str | None = None,
    rule: str | None = None,
) -> Issue:
    """Build a finding from an issue the schema defines: ``{code, level, message}``.

    Parameters
    ----------
    definition : Mapping
        The schema's issue block: a ``rules.checks`` rule's ``issue``, a field
        requirement's ``issue``, or an entry of ``rules.errors``.
    location : str or None
        Dataset-relative path of the file, without a leading ``/``.
    severity : Severity, optional
        Overrides the block's ``level``. A field requirement's issue leaves ``level``
        out, because the requirement's own level decides it.
    message : str, optional
        A message specific to this file, used instead of the schema's general one.
    sub_code, rule : str, optional
        Copied onto the finding.

    Returns
    -------
    Issue
        The finding. The schema's multi-line YAML message becomes one line.

    """
    code = str(definition.get('code'))
    if severity is None:
        level = definition.get('level')
        severity = Severity.from_level(str(level)) if level else _reference_severity(code)
    if message is None:
        message = _one_line(definition.get('message'))
    return Issue(
        code=code,
        severity=severity,
        location=location,
        message=message,
        sub_code=sub_code,
        rule=rule,
    )


def coded_issue(
    schema: Mapping[str, Any],
    code: str,
    *,
    location: str | None,
    message: str | None = None,
    sub_code: str | None = None,
    rule: str | None = None,
) -> Issue:
    """Build a finding for a known code, wherever the code is defined.

    The schema's ``rules.errors`` wins when it defines the code (level and message
    then come from the schema); otherwise :data:`REFERENCE_CODES` supplies them.

    Parameters
    ----------
    schema : Mapping
        The BIDS schema.
    code : str
        A code from ``rules.errors`` or :data:`REFERENCE_CODES`.
    location, message, sub_code, rule
        As for :func:`schema_issue`. ``message`` replaces the general reason.

    Returns
    -------
    Issue
        The finding.

    Raises
    ------
    KeyError
        For a code defined in neither place: a typo in a check, caught by the tests.

    """
    definition = _schema_errors(schema).get(code)
    if definition is not None:
        return schema_issue(
            definition, location=location, message=message, sub_code=sub_code, rule=rule
        )
    severity, reason = REFERENCE_CODES[code]
    return Issue(
        code=code,
        severity=severity,
        location=location,
        message=message if message is not None else reason,
        sub_code=sub_code,
        rule=rule,
    )


def _schema_errors(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Index ``rules.errors`` by issue code, once per schema."""
    cached = _SCHEMA_ERRORS_MEMO.get(id(schema))
    if cached is None:
        errors = schema['rules'].get('errors', {})
        cached = {str(errors[name].get('code', name)): errors[name] for name in errors}
        _SCHEMA_ERRORS_MEMO[id(schema)] = cached
    return cached


def _reference_severity(code: str) -> Severity:
    """Return the reference validator's severity for a code, or error if it has none."""
    return REFERENCE_CODES.get(code, (Severity.ERROR, ''))[0]


def _one_line(message: Any) -> str | None:
    """Turn a multi-line YAML message into one line; None stays None."""
    return ' '.join(str(message).split()) if message else None


__all__ = [
    'REFERENCE_CODES',
    'DatasetIssues',
    'Issue',
    'Severity',
    'coded_issue',
    'schema_issue',
]
