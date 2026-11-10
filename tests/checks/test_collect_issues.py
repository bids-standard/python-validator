"""Tests for running every check in one walk."""

import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator import context as context_module
from bids_validator.checks import DATASET_CHECKS, FILE_CHECKS, FOLDER_CHECKS, collect_issues
from bids_validator.checks.filenames import filename_issues, folder_issues
from bids_validator.checks.inheritance import inheritance_issues
from bids_validator.checks.integrity import dataset_integrity_issues, integrity_issues
from bids_validator.checks.rules import rule_issues
from bids_validator.context import Context
from bids_validator.issues import Issue
from bids_validator.types.files import FileTree

from ..helpers import build, clean_dataset, findings, write


def test_the_order_of_the_checks() -> None:
    """Reading problems first, then the name, then the schema rules: the reference order."""
    assert DATASET_CHECKS == (dataset_integrity_issues,)
    assert FOLDER_CHECKS == (folder_issues,)
    assert FILE_CHECKS == (integrity_issues, inheritance_issues, filename_issues, rule_issues)


def test_one_walk_reports_what_each_check_reports(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Running the checks together loses nothing and adds nothing."""
    build(
        tmp_path,
        'sub-01/anat/sub-01_T1w.nii.gz',
        'sub-01/anat/sub-01_T1w.nii',  # DUPLICATE_FILES (a rule)
        'sub-01/func/sub-01_bold.nii.gz',  # MISSING_REQUIRED_ENTITY (a filename check)
        'sub-01/foo/',  # NOT_INCLUDED (a folder check)
    )  # empty images: EMPTY_FILE and NIFTI_HEADER_UNREADABLE (integrity)
    together = sorted(findings(tmp_path, schema))
    apart = sorted(
        finding
        for check in FOLDER_CHECKS + FILE_CHECKS
        for finding in findings(tmp_path, schema, check)
    )
    assert together == apart
    codes = {code for code, _ in together}
    assert {'MISSING_REQUIRED_ENTITY', 'DUPLICATE_FILES', 'EMPTY_FILE', 'NOT_INCLUDED'} <= codes


def test_folders_get_the_folder_checks_and_files_the_file_checks(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A plain folder is never given to a file check; a directory recording is a file."""
    build(tmp_path, 'sub-01/foo/', 'sub-01/meg/sub-01_task-x_meg.ds/x.meg4')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    seen: list[str] = []

    def record(context: Context) -> list[Issue]:
        seen.append(context.file.relative_path)
        return []

    collect_issues(tree, schema, dataset_checks=(), folder_checks=(), file_checks=(record,))
    assert 'sub-01/meg/sub-01_task-x_meg.ds/' in seen
    assert 'sub-01/foo/' not in seen
    assert 'sub-01/' not in seen


def test_each_file_s_inheritance_chain_is_found_once(
    tmp_path: pathlib.Path, schema: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checks that need the JSON files a file inherits from share one search."""
    write(
        tmp_path,
        {
            'task-rest_bold.json': {'TaskName': 'rest', 'RepetitionTime': 2},
            'sub-01/func/sub-01_task-rest_bold.json': {'RepetitionTime': 3},
            'sub-01/func/sub-01_task-rest_bold.nii.gz': b'',
        },
    )
    searched: list[str] = []
    search = context_module._sidecar_files

    def counted_search(file: FileTree) -> tuple[FileTree, ...]:
        searched.append(file.relative_path)
        return search(file)

    monkeypatch.setattr(context_module, '_sidecar_files', counted_search)
    issues = collect_issues(FileTree.read_from_filesystem(str(tmp_path)), schema)
    assert 'SIDECAR_FIELD_OVERRIDE' in {issue.code for issue in issues}  # the chain was read
    assert 'sub-01/func/sub-01_task-rest_bold.nii.gz' in searched
    assert len(searched) == len(set(searched))


def test_dataset_checks_come_first(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/notes.txt')
    (tmp_path / 'dataset_description.json').unlink()
    issues = collect_issues(FileTree.read_from_filesystem(str(tmp_path)), schema)
    assert issues.issues[0].code == 'MISSING_DATASET_DESCRIPTION'


def test_a_clean_dataset_is_clean(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """The dataset the CLI tests use has no finding at all."""
    assert findings(clean_dataset(tmp_path), schema) == []
