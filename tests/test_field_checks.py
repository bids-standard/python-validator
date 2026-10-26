"""Tests for required and recommended JSON fields, their values, and overrides."""

import json
import pathlib

from bidsschematools.types.namespace import Namespace

from bids_validator.checks import collect_issues
from bids_validator.context import Context, Dataset
from bids_validator.field_checks import field_issues, inheritance_issues
from bids_validator.issues import Issue, Severity
from bids_validator.rule_checks import rule_issues
from bids_validator.types.files import FileTree

from .helpers import FULL_DESCRIPTION, nifti, write

BOLD = 'sub-01/func/sub-01_task-rest_bold.nii.gz'


def rule_findings(root: pathlib.Path, schema: Namespace) -> list[Issue]:
    tree = FileTree.read_from_filesystem(str(root))
    return list(collect_issues(tree, schema, checks=(rule_issues,), dataset_checks=()))


def keyed(issues: list[Issue]) -> set[tuple[str, str | None, str | None]]:
    return {(i.code, i.location, i.sub_code) for i in issues}


def test_missing_required_and_recommended_sidecar_fields(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    write(tmp_path, {BOLD: nifti((2, 2, 2, 3)), 'sub-01/func/sub-01_task-rest_bold.json': {}})
    issues = rule_findings(tmp_path, schema)
    found = keyed(issues)
    assert ('SIDECAR_KEY_REQUIRED', BOLD, 'TaskName') in found
    assert ('SIDECAR_KEY_REQUIRED', BOLD, 'RepetitionTime') in found
    assert ('SIDECAR_KEY_RECOMMENDED', BOLD, 'Manufacturer') in found
    severities = {i.sub_code: i.severity for i in issues if i.code.startswith('SIDECAR_KEY')}
    assert severities['TaskName'] is Severity.ERROR
    assert severities['Manufacturer'] is Severity.WARNING


def test_a_present_field_is_not_reported_missing(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    write(
        tmp_path,
        {
            BOLD: nifti((2, 2, 2, 3)),
            'task-rest_bold.json': {'TaskName': 'rest', 'RepetitionTime': 2.0},
        },
    )
    missing = {
        i.sub_code for i in rule_findings(tmp_path, schema) if i.code == 'SIDECAR_KEY_REQUIRED'
    }
    assert 'TaskName' not in missing
    assert 'RepetitionTime' not in missing


def test_json_rules_read_the_file_itself(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {}, description={'Name': 'x', 'BIDSVersion': '1.11.1'})
    found = keyed(rule_findings(tmp_path, schema))
    assert ('JSON_KEY_RECOMMENDED', 'dataset_description.json', 'DatasetType') in found
    # Authors carries its own issue in the schema, used instead of JSON_KEY_RECOMMENDED.
    assert ('NO_AUTHORS', 'dataset_description.json', 'Authors') in found


def test_a_field_can_carry_its_own_issue(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """A fieldmap without IntendedFor or B0FieldIdentifier gets the field's own code."""
    write(
        tmp_path,
        {
            'sub-01/fmap/sub-01_magnitude1.nii.gz': nifti((2, 2, 2)),
            'sub-01/fmap/sub-01_magnitude1.json': {},
        },
    )
    [issue] = [
        i for i in rule_findings(tmp_path, schema) if i.code == 'B0_FIELD_IDENTIFIER_RECOMMENDED'
    ]
    assert issue.severity is Severity.WARNING  # from the field's level: recommended
    assert issue.sub_code == 'B0FieldIdentifier'
    assert issue.message is not None
    assert issue.message.startswith('File is missing B0FieldIdentifier metadata')


def test_derivatives_make_fields_optional(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """Unless a rule is written for derivatives, as the specification says."""
    write(
        tmp_path,
        {BOLD: nifti((2, 2, 2, 3)), 'sub-01/func/sub-01_task-rest_bold.json': {}},
        description={**FULL_DESCRIPTION, 'DatasetType': 'derivative'},
    )
    missing = [i for i in rule_findings(tmp_path, schema) if i.code.startswith('SIDECAR_KEY')]
    assert missing, 'the derivative rules still apply'
    assert all(i.rule and i.rule.startswith('rules.sidecars.derivatives') for i in missing)


def test_a_level_addendum_can_raise_the_level(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(
        tmp_path,
        {
            BOLD: nifti((2, 2, 2, 3)),
            'sub-01/func/sub-01_task-rest_bold.json': {'M0Type': 'Estimate'},
        },
    )
    tree = FileTree.read_from_filesystem(str(tmp_path))
    context = Context(
        tree / 'sub-01' / 'func' / 'sub-01_task-rest_bold.nii.gz', Dataset(tree, schema), None
    )
    rule = {
        'selectors': [],
        'fields': {
            'M0Estimate': {
                'level': 'optional',
                'level_addendum': 'required if `M0Type` is `Estimate`',
            }
        },
    }
    [issue] = field_issues('rules.sidecars.test.Rule', rule, context)
    assert (issue.code, issue.severity) == ('SIDECAR_KEY_REQUIRED', Severity.ERROR)


def test_a_wrong_sidecar_value_is_reported_once_where_it_is_written(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A root sidecar shared by two runs: one finding, on the root sidecar."""
    write(
        tmp_path,
        {
            BOLD: nifti((2, 2, 2, 3)),
            'sub-02/func/sub-02_task-rest_bold.nii.gz': nifti((2, 2, 2, 3)),
            'task-rest_bold.json': {'TaskName': 'rest', 'RepetitionTime': -2.0},
        },
    )
    wrong = [
        i for i in rule_findings(tmp_path, schema) if i.code == 'JSON_SCHEMA_VALIDATION_ERROR'
    ]
    assert [(i.location, i.sub_code, i.message) for i in wrong] == [
        ('task-rest_bold.json', 'RepetitionTime', 'RepetitionTime must be > 0')
    ]


def test_a_wrong_value_in_a_json_file(tmp_path: pathlib.Path, schema: Namespace) -> None:
    write(tmp_path, {}, description={**FULL_DESCRIPTION, 'Authors': 'Ada Lovelace'})
    wrong = [
        i for i in rule_findings(tmp_path, schema) if i.code == 'JSON_SCHEMA_VALIDATION_ERROR'
    ]
    # Two rules list Authors, and each checks it, as in the reference validator.
    assert {(i.location, i.sub_code, i.message) for i in wrong} == {
        ('dataset_description.json', 'Authors', 'Authors must be array')
    }


def test_a_json_file_gets_no_sidecar_rules(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """It is a sidecar; it does not have one."""
    write(tmp_path, {BOLD: nifti((2, 2, 2, 3)), 'sub-01/func/sub-01_task-rest_bold.json': {}})
    locations = {
        i.location for i in rule_findings(tmp_path, schema) if i.code.startswith('SIDECAR_KEY')
    }
    assert locations == {BOLD}


def overrides(root: pathlib.Path, schema: Namespace) -> list[Issue]:
    tree = FileTree.read_from_filesystem(str(root))
    return list(collect_issues(tree, schema, checks=(inheritance_issues,), dataset_checks=()))


def test_a_deeper_sidecar_changing_a_value_is_warned(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    write(
        tmp_path,
        {
            BOLD: nifti((2, 2, 2, 3)),
            'task-rest_bold.json': {'RepetitionTime': 2.0},
            'sub-01/func/sub-01_task-rest_bold.json': {'RepetitionTime': 3.0},
        },
    )
    [issue] = overrides(tmp_path, schema)
    assert (issue.code, issue.severity) == ('SIDECAR_FIELD_OVERRIDE', Severity.WARNING)
    assert (issue.location, issue.sub_code) == (
        'sub-01/func/sub-01_task-rest_bold.json',
        'RepetitionTime',
    )


def test_the_same_value_twice_is_not_an_override(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Compared by content: the same list written at two levels is fine."""
    filters = {'Notch': {'Frequency': 50}}
    write(
        tmp_path,
        {
            BOLD: nifti((2, 2, 2, 3)),
            'task-rest_bold.json': {'SoftwareFilters': filters, 'SliceTiming': [0, 1]},
            'sub-01/func/sub-01_task-rest_bold.json': {
                'SoftwareFilters': json.loads(json.dumps(filters)),
                'SliceTiming': [0, 1],
            },
        },
    )
    assert overrides(tmp_path, schema) == []
