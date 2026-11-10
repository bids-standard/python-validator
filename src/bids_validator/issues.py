"""What a finding is: the data model of everything the validator reports.

This module holds data only. It reads no file and no schema. The checks that produce
findings, and the codes each of them can report, live in the check modules of
:mod:`bids_validator.checks` (``integrity``, ``inheritance``, ``filenames``,
``expressions``, ``fields``, ``tables``).

Three types:

* :class:`IssueDefinition` is a KIND of finding: a code, how serious it is, and the
  general reason it exists. ``EMPTY_FILE`` is one. A check module either reads its
  definitions from the schema (:meth:`IssueDefinition.from_schema`) or, for a code the
  schema does not define, lists it beside the checks that report it.
* :class:`Issue` is one finding: a definition met at one place in a dataset, with a
  message about that place. :meth:`IssueDefinition.make_issue` makes one.
* :class:`DatasetIssues` is every finding of one validation, in order.

The shape follows the reference validator (bids-validator, ``src/types/issues.ts``),
so a report can be compared with its output.
"""

# Lets a type hint name a class defined further down this file (``IssueDefinition``
# returns ``Issue``, ``from_level`` returns ``Severity``) without quoting it.
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from enum import Enum
from typing import Any

# attrs writes the boring parts of a data class for us (``__init__``, ``__repr__``,
# ``__eq__``) from the attribute list; see the decorators on the classes below.
import attrs

# The names other modules are meant to import from this one.
__all__ = ['DatasetIssues', 'Issue', 'IssueDefinition', 'Severity']


class Severity(str, Enum):
    """How serious a finding is.

    ``WARNING`` asks for attention; ``ERROR`` means the dataset is not valid BIDS.
    Subclassing ``str`` keeps the values JSON-friendly: a member serialises directly
    to ``'warning'`` or ``'error'``.
    """

    WARNING = 'warning'
    ERROR = 'error'

    @classmethod
    def from_level(cls, level: str) -> Severity:
        """Return the severity for a schema issue ``level``.

        The schema writes ``level: warning`` or ``level: error``. Anything other than
        ``warning`` is treated as an error, so an unexpected value is never silently
        downgraded.
        """
        return cls.WARNING if level == 'warning' else cls.ERROR


# ``attrs.define`` turns the annotated attributes below into a class with an
# ``__init__(code, severity=..., ...)``; ``kw_only=True`` means every argument must be
# given by name (``Issue(code='X', location='a')``), so they cannot be swapped by mistake.
@attrs.define(kw_only=True)
class Issue:
    """One finding: a problem met at one place in a dataset.

    Attributes
    ----------
    code
        Stable identifier of the kind of problem, the reference validator's
        (for example ``'FILENAME_MISMATCH'``).
    severity
        How serious the finding is. Defaults to :attr:`Severity.ERROR`.
    location
        Dataset-relative path of the file the finding is about, without a leading
        ``/``; ``None`` for a finding about the dataset as a whole.
    message
        What is wrong at this place, for a person to read.
    sub_code
        Optional finer category within ``code``, such as the name of a field.
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


# ``attrs.frozen`` is ``attrs.define`` with the attributes made read-only: a definition
# is shared by every finding of its kind, so nothing may change it.
@attrs.frozen
class IssueDefinition:
    """A kind of finding: a code, its severity, and why it is a problem.

    A check reports one by making an :class:`Issue` from it, with the place it found it::

        EMPTY_FILE.make_issue('sub-01/anat/sub-01_T1w.nii.gz')

    Attributes
    ----------
    code
        The identifier every finding of this kind carries.
    severity
        How serious every finding of this kind is.
    reason
        Why this kind of finding is a problem, in general. A finding whose check has
        nothing more specific to say uses it as its message.

    """

    code: str
    severity: Severity
    reason: str

    # A classmethod is called on the class, not on an instance:
    # ``IssueDefinition.from_schema(block)``. It is a second way to build one.
    @classmethod
    def from_schema(
        cls, block: Mapping[str, Any], *, severity: Severity | None = None
    ) -> IssueDefinition:
        """Build a definition from an issue block the schema writes.

        The schema writes the same three keys wherever it defines an issue: in
        ``rules.errors``, in each ``rules.checks`` rule, and on some fields of the
        ``rules.sidecars`` rules::

            code: README_FILE_SMALL
            level: warning
            message: |
              The recommended file '/README' is very small. ...

        Parameters
        ----------
        block : Mapping
            The issue block.
        severity : Severity, optional
            Used instead of the block's ``level``. A field's issue block has no level
            of its own: the field's requirement level decides how serious it is.

        Returns
        -------
        IssueDefinition
            The definition. The YAML message, written over several lines, becomes one.

        """
        if severity is None:
            severity = Severity.from_level(str(block.get('level', '')))
        return cls(
            code=str(block['code']),
            severity=severity,
            reason=' '.join(str(block.get('message', '')).split()),
        )

    def make_issue(
        self,
        location: str | None,
        *,
        message: str | None = None,
        sub_code: str | None = None,
        rule: str | None = None,
    ) -> Issue:
        """Return a finding of this kind, found at ``location``.

        Parameters
        ----------
        location : str or None
            Dataset-relative path of the file, without a leading ``/``; ``None`` for
            the dataset as a whole.
        message : str, optional
            What is wrong at this place. Defaults to the definition's general reason.
        sub_code, rule : str, optional
            Copied onto the finding (see :class:`Issue`).

        Returns
        -------
        Issue
            The finding.

        """
        return Issue(
            code=self.code,
            severity=self.severity,
            location=location,
            message=self.reason if message is None else message,
            sub_code=sub_code,
            rule=rule,
        )


# ``attrs.define`` again; ``attrs.field(factory=list)`` gives every new container its own
# empty list (a plain ``= []`` default would be one list shared by all of them).
@attrs.define
class DatasetIssues:
    """Every finding of one validation, in the order the checks reported them.

    A thin wrapper over a list, so a report has a stable container that is easy to
    extend (filtering, severity rollup) without changing the code that fills it.

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

    # A property is read like an attribute, without brackets: ``issues.has_errors``.
    @property
    def has_errors(self) -> bool:
        """Whether any finding is an error (used to drive a non-zero exit code)."""
        return any(issue.severity is Severity.ERROR for issue in self.issues)

    # These two make the container behave like a list: ``for issue in issues`` and
    # ``len(issues)`` work on it directly.
    def __iter__(self) -> Iterator[Issue]:
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)
