"""Tests for table columns: presence, order, extra columns, value types, unique index."""

import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.checks import collect_issues
from bids_validator.checks.rules import rule_issues
from bids_validator.issues import Issue, Severity
from bids_validator.types.files import FileTree

from ..helpers import write

CHANNELS = 'sub-01/eeg/sub-01_task-rest_channels.tsv'


def table_findings(root: pathlib.Path, schema: Namespace) -> list[Issue]:
    tree = FileTree.read_from_filesystem(str(root))
    issues = collect_issues(
        tree, schema, dataset_checks=(), folder_checks=(), file_checks=(rule_issues,)
    )
    return [issue for issue in issues if issue.code.startswith('TSV_')]


def keyed(issues: list[Issue]) -> set[tuple[str, str | None, str | None]]:
    return {(i.code, i.location, i.sub_code) for i in issues}


def test_a_required_initial_column_missing(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {CHANNELS: 'name\ttype\nFz\tEEG\n'})
    assert ('TSV_COLUMN_MISSING', CHANNELS, 'units') in keyed(table_findings(tmp_path, schema))


def test_initial_columns_out_of_order(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {CHANNELS: 'type\tname\tunits\nEEG\tFz\tuV\n'})
    found = keyed(table_findings(tmp_path, schema))
    assert ('TSV_COLUMN_ORDER_INCORRECT', CHANNELS, 'name') in found
    assert ('TSV_COLUMN_ORDER_INCORRECT', CHANNELS, 'type') in found


@pytest.mark.parametrize(
    ('files', 'location', 'code', 'severity'),
    [
        pytest.param(
            {CHANNELS: 'name\ttype\tunits\tfoo\nFz\tEEG\tuV\t1\n'},
            CHANNELS,
            'TSV_ADDITIONAL_COLUMNS_MUST_DEFINE',
            Severity.ERROR,
            id='allowed-if-defined',
        ),
        pytest.param(
            {'participants.tsv': 'participant_id\tgroup\nsub-01\ta\n'},
            'participants.tsv',
            'TSV_ADDITIONAL_COLUMNS_UNDEFINED',
            Severity.WARNING,
            id='allowed',
        ),
    ],
)
def test_extra_columns(
    tmp_path: pathlib.Path,
    schema: Namespace,
    files: dict[str, str],
    location: str,
    code: str,
    severity: Severity,
) -> None:
    write(tmp_path, files)
    [issue] = [i for i in table_findings(tmp_path, schema) if i.code == code]
    assert (issue.location, issue.severity) == (location, severity)


def test_an_extra_column_defined_in_the_sidecar(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """Defined, so allowed; and its values follow the sidecar's definition."""
    write(
        tmp_path,
        {
            'participants.tsv': 'participant_id\tgroup\nsub-01\ta\nsub-02\tc\n',
            'participants.json': {'group': {'Levels': {'a': 'A', 'b': 'B'}}},
        },
    )
    issues = table_findings(tmp_path, schema)
    assert [(i.code, i.sub_code, i.message) for i in issues] == [
        ('TSV_VALUE_INCORRECT_TYPE', 'group', "line 3: 'c'")
    ]


@pytest.mark.parametrize(
    ('column', 'value', 'code'),
    [
        ('age', '30', None),
        ('age', 'n/a', None),  # always accepted
        ('age', 'thirty', 'TSV_VALUE_INCORRECT_TYPE'),
        ('age', '95', 'TSV_VALUE_INCORRECT_TYPE'),  # above the schema's Maximum of 89
        ('age', '89+', 'TSV_PSEUDO_AGE_DEPRECATED'),
        ('sex', 'F', None),
        ('sex', 'X', 'TSV_VALUE_INCORRECT_TYPE'),  # not one of the levels
    ],
)
def test_value_types(
    tmp_path: pathlib.Path, schema: Namespace, column: str, value: str, code: str | None
) -> None:
    write(tmp_path, {'participants.tsv': f'participant_id\t{column}\nsub-01\t{value}\n'})
    assert [i.code for i in table_findings(tmp_path, schema)] == ([code] if code else [])


def test_a_near_miss_of_n_a_gets_a_hint(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {'participants.tsv': 'participant_id\tage\nsub-01\tNA\n'})
    [issue] = table_findings(tmp_path, schema)
    assert issue.message == "line 2: 'NA', did you mean 'n/a'?"


def test_only_the_first_bad_value_of_a_column(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {'participants.tsv': 'participant_id\tage\nsub-01\tx\nsub-02\ty\n'})
    assert len(table_findings(tmp_path, schema)) == 1


def test_a_sidecar_contradicting_the_schema(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """``participant_id`` is text in the schema; a sidecar cannot make it a number."""
    write(
        tmp_path,
        {
            'participants.tsv': 'participant_id\nsub-01\n',
            'participants.json': {'participant_id': {'Format': 'number'}},
        },
    )
    [issue] = table_findings(tmp_path, schema)
    assert (issue.code, issue.location, issue.sub_code) == (
        'TSV_COLUMN_TYPE_REDEFINED',
        'participants.json',  # reported where the redefinition is written
        'participant_id',
    )


def test_index_values_must_be_unique(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {'participants.tsv': 'participant_id\nsub-01\nsub-01\n'})
    [issue] = table_findings(tmp_path, schema)
    assert (issue.code, issue.message) == ('TSV_INDEX_VALUE_NOT_UNIQUE', "row 3, value 'sub-01'")


def test_a_column_name_with_a_dot(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """``key_resp.rt`` (as PsychoPy writes it) is an ordinary column, not a path."""
    write(
        tmp_path,
        {
            'participants.tsv': 'participant_id\tkey_resp.rt\nsub-01\t0.5\nsub-02\tslow\n',
            'participants.json': {'key_resp.rt': {'Description': 'Response time', 'Units': 's'}},
        },
    )
    issues = table_findings(tmp_path, schema)
    assert [(i.code, i.sub_code) for i in issues] == [('TSV_VALUE_INCORRECT_TYPE', 'key_resp.rt')]
