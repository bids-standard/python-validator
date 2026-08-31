"""Unit tests for the issues model (pure data, no fixtures needed)."""

import attrs
import pytest

from bids_validator.issues import DatasetIssues, Issue, Severity


def test_issue_defaults() -> None:
    issue = Issue(code='FILENAME_MISMATCH')
    assert issue.code == 'FILENAME_MISMATCH'
    assert issue.severity is Severity.ERROR
    assert issue.location is None
    assert issue.message is None
    assert issue.sub_code is None


@pytest.mark.parametrize('severity', [Severity.WARNING, Severity.ERROR])
def test_issue_severity_roundtrip(severity: Severity) -> None:
    issue = Issue(code='X', severity=severity)
    assert issue.severity is severity
    assert issue.severity.value in ('warning', 'error')


def test_dataset_issues_add_extend_and_order() -> None:
    issues = DatasetIssues()
    assert len(issues) == 0
    issues.add(Issue(code='A'))
    issues.extend([Issue(code='B', severity=Severity.WARNING), Issue(code='C')])
    assert len(issues) == 3
    assert [issue.code for issue in issues] == ['A', 'B', 'C']


def test_by_severity() -> None:
    issues = DatasetIssues()
    issues.extend(
        [
            Issue(code='A', severity=Severity.ERROR),
            Issue(code='B', severity=Severity.WARNING),
            Issue(code='C', severity=Severity.ERROR),
        ]
    )
    assert [issue.code for issue in issues.by_severity(Severity.ERROR)] == ['A', 'C']
    assert [issue.code for issue in issues.by_severity(Severity.WARNING)] == ['B']


def test_has_errors() -> None:
    issues = DatasetIssues()
    assert issues.has_errors is False
    issues.add(Issue(code='W', severity=Severity.WARNING))
    assert issues.has_errors is False
    issues.add(Issue(code='E', severity=Severity.ERROR))
    assert issues.has_errors is True


def test_issue_is_json_ready() -> None:
    issue = Issue(code='X', severity=Severity.ERROR, location='/a', message='m')
    data = attrs.asdict(issue)
    assert data['code'] == 'X'
    assert data['severity'] == 'error'
    assert data['location'] == '/a'
