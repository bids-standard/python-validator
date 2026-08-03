"""Tests for the schema-driven filename checks (names and paths only)."""

import json
import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator import BIDSValidator
from bids_validator.filename_checks import (
    DEFAULT_IGNORES,
    FILENAME_ISSUES,
    collect_filename_issues,
)
from bids_validator.issues import Severity
from bids_validator.types.files import FileTree

VALID = 'sub-01/anat/sub-01_T1w.nii.gz'


def build(root: pathlib.Path, *relpaths: str) -> pathlib.Path:
    """Create a minimal dataset containing the given files."""
    (root / 'dataset_description.json').write_text(
        json.dumps({'Name': 'test', 'BIDSVersion': '1.11.1'})
    )
    for relpath in relpaths:
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'')
    return root


def codes(root: pathlib.Path, schema: Namespace) -> dict[str, list[str]]:
    """Map each emitted issue code to the locations it was emitted for."""
    tree = FileTree.read_from_filesystem(str(root))
    out: dict[str, list[str]] = {}
    for issue in collect_filename_issues(tree, schema):
        out.setdefault(issue.code, []).append(issue.location or '')
    return out


def test_valid_dataset_has_no_findings(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, VALID, 'sub-01/func/sub-01_task-rest_bold.nii.gz', 'README')
    assert codes(tmp_path, schema) == {}


@pytest.mark.parametrize(
    ('relpath', 'expected'),
    [
        ('sub-01/notes.txt', 'NOT_INCLUDED'),
        ('sub-01/anat/sub-01_T1w.txt', 'EXTENSION_MISMATCH'),
        ('sub-01/func/sub-01_bold.nii.gz', 'MISSING_REQUIRED_ENTITY'),
        ('sub-01/anat/sub-01_acq-_T1w.nii.gz', 'ENTITY_WITH_NO_LABEL'),
        ('sub-01/anat/sub-01_acq-a!b_T1w.nii.gz', 'INVALID_ENTITY_LABEL'),
        ('sub-01/anat/sub-01_dir-AP_T1w.nii.gz', 'ENTITY_NOT_IN_RULE'),
        ('sub-01/anat/acq-x_sub-01_T1w.nii.gz', 'FILENAME_MISMATCH'),
        ('sub-01/func/sub-01_T1w.nii.gz', 'DATATYPE_MISMATCH'),
        ('sub-02/anat/sub-01_T1w.nii.gz', 'INVALID_LOCATION'),
    ],
)
def test_each_code_fires(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str, expected: str
) -> None:
    build(tmp_path, relpath)
    found = codes(tmp_path, schema)
    assert expected in found, f'{relpath} should raise {expected}, got {sorted(found)}'
    assert relpath in found[expected]


def test_findings_are_errors_and_carry_location(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/notes.txt')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    issues = collect_filename_issues(tree, schema)
    assert len(issues) == 1
    assert issues.has_errors
    issue = issues.issues[0]
    assert issue.severity is Severity.ERROR
    assert issue.location == 'sub-01/notes.txt'
    assert issue.message


def test_rule_path_recorded_for_rule_scoped_findings(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    build(tmp_path, 'sub-01/func/sub-01_bold.nii.gz')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    issue = next(i for i in collect_filename_issues(tree, schema))
    assert issue.code == 'MISSING_REQUIRED_ENTITY'
    assert issue.rule is not None
    assert issue.rule.startswith('rules.files.')


def test_default_ignores_are_not_flagged(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, VALID, '.DS_Store', 'sub-01/.DS_Store', 'code/script.py')
    assert codes(tmp_path, schema) == {}


def test_bidsignore_is_respected(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, VALID, 'extras/notes.txt')
    assert 'NOT_INCLUDED' in codes(tmp_path, schema)

    (tmp_path / '.bidsignore').write_text('extras/\n')
    assert codes(tmp_path, schema) == {}


def test_catalog_documents_every_emitted_code() -> None:
    assert 'NOT_INCLUDED' in FILENAME_ISSUES
    assert len(FILENAME_ISSUES) == 10
    assert all(reason for reason in FILENAME_ISSUES.values())
    assert '.*' in DEFAULT_IGNORES


@pytest.mark.parametrize(
    'relpath',
    [
        'sub-01/foo/sub-01_T1w.nii.gz',  # a folder that is not a datatype
        'sub-01/sub-01_T1w.nii.gz',  # no datatype folder at all
    ],
)
def test_data_file_outside_datatype_directory(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str
) -> None:
    """Stricter than the reference validator, and matches legacy is_bids."""
    build(tmp_path, relpath)
    found = codes(tmp_path, schema)
    assert 'INVALID_LOCATION' in found
    assert relpath in found['INVALID_LOCATION']
    # the legacy check agrees these are not valid BIDS paths
    assert not BIDSValidator().is_bids(f'/{relpath}')


@pytest.mark.parametrize(
    'relpath',
    [
        'task-rest_bold.json',  # inherited sidecar at the dataset root
        'sub-01/sub-01_T1w.json',  # sidecar one level above the data
        'sub-01/sub-01_scans.tsv',  # subject-level tabular metadata
        'sub-01/sub-01_task-rest_events.tsv',  # events inherited upward
    ],
)
def test_inheritable_metadata_may_sit_above_the_datatype_directory(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str
) -> None:
    """The inheritance principle allows these; they must not be flagged."""
    build(tmp_path, VALID, relpath)
    assert codes(tmp_path, schema) == {}
    assert BIDSValidator().is_bids(f'/{relpath}')
