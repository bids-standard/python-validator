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
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import Enum

import attrs


class Severity(str, Enum):
    """How serious a finding is.

    Ordered from low to high attention: ``WARNING`` then ``ERROR``. Subclassing
    ``str`` keeps the values JSON-friendly, so a member serialises directly to
    ``'warning'`` or ``'error'``.
    """

    WARNING = 'warning'
    ERROR = 'error'


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


__all__ = ['DatasetIssues', 'Issue', 'Severity']
