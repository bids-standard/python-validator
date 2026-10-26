"""Tests for running every check family in one walk."""

import pathlib

from bidsschematools.types.namespace import Namespace

from bids_validator.checks import PER_DATASET_CHECKS, PER_FILE_CHECKS, collect_issues
from bids_validator.field_checks import inheritance_issues
from bids_validator.filename_checks import filename_issues
from bids_validator.integrity_checks import dataset_integrity_issues, integrity_issues
from bids_validator.rule_checks import rule_issues
from bids_validator.types.files import FileTree

from .helpers import build, clean_dataset, findings


def test_the_order_of_the_checks() -> None:
    """Reading problems first, then the name, then the schema rules: the reference order."""
    assert PER_FILE_CHECKS == (integrity_issues, inheritance_issues, filename_issues, rule_issues)
    assert PER_DATASET_CHECKS == (dataset_integrity_issues,)


def test_one_walk_reports_what_each_family_reports(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Running the families together loses nothing and adds nothing."""
    build(
        tmp_path,
        'sub-01/anat/sub-01_T1w.nii.gz',
        'sub-01/anat/sub-01_T1w.nii',  # DUPLICATE_FILES (a rule)
        'sub-01/func/sub-01_bold.nii.gz',  # MISSING_REQUIRED_ENTITY (a filename check)
    )  # empty images: EMPTY_FILE and NIFTI_HEADER_UNREADABLE (integrity)
    together = sorted(findings(tmp_path, schema))
    apart = sorted(
        finding for check in PER_FILE_CHECKS for finding in findings(tmp_path, schema, check)
    )
    assert together == apart
    codes = {code for code, _ in together}
    assert {'MISSING_REQUIRED_ENTITY', 'DUPLICATE_FILES', 'EMPTY_FILE'} <= codes


def test_dataset_checks_come_first(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/notes.txt')
    (tmp_path / 'dataset_description.json').unlink()
    issues = collect_issues(FileTree.read_from_filesystem(str(tmp_path)), schema)
    assert issues.issues[0].code == 'MISSING_DATASET_DESCRIPTION'


def test_a_clean_dataset_is_clean(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """The dataset the CLI tests use has no finding at all."""
    assert findings(clean_dataset(tmp_path), schema) == []
