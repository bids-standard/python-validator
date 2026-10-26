"""Unit tests for the issues model (pure data, no fixtures needed)."""

import attrs
import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.issues import DatasetIssues, Issue, Severity, coded_issue, schema_issue


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


def test_schema_issue_reads_code_level_and_message() -> None:
    definition = {'code': 'X_CODE', 'level': 'warning', 'message': 'A message\nover two lines.\n'}
    issue = schema_issue(definition, location='a.json', rule='rules.checks.x.Y')
    assert (issue.code, issue.severity, issue.message) == (
        'X_CODE',
        Severity.WARNING,
        'A message over two lines.',
    )


def test_schema_issue_severity_can_come_from_elsewhere() -> None:
    """A field's issue leaves out its level: the field's requirement decides it."""
    issue = schema_issue({'code': 'X', 'message': 'm'}, location=None, severity=Severity.ERROR)
    assert issue.severity is Severity.ERROR


def test_coded_issue_prefers_the_schema(schema: Namespace) -> None:
    # EMPTY_FILE is defined in rules.errors: its message is the schema's.
    issue = coded_issue(schema, 'EMPTY_FILE', location='x.nii')
    assert issue.message == ' '.join(str(schema.rules.errors.EmptyFile.message).split())
    # TSV_EMPTY_LINE is not: severity and reason come from the reference catalog.
    issue = coded_issue(schema, 'TSV_EMPTY_LINE', location='x.tsv')
    assert issue.severity is Severity.ERROR
    assert issue.message == 'An empty line was found in the TSV file.'


def test_coded_issue_refuses_an_unknown_code(schema: Namespace) -> None:
    import pytest

    with pytest.raises(KeyError):
        coded_issue(schema, 'NO_SUCH_CODE', location=None)
