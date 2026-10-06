"""Tests for the command line.

The CLI is a thin front end over :mod:`bids_validator.filename_checks`. These tests
cover the part that is genuinely the CLI's own: what it prints, and what it exits with.
The last test is the important one. It pins the CLI to the module, so the duplicated
walk that used to live in ``__main__`` cannot creep back in.
"""

import pathlib

import pytest
from bidsschematools.types.namespace import Namespace
from typer.testing import CliRunner

from bids_validator.__main__ import app, validate
from bids_validator.filename_checks import collect_filename_issues
from bids_validator.issues import Severity
from bids_validator.types.files import FileTree

from .test_filename_checks import VALID, build

runner = CliRunner()

BROKEN = 'sub-01/func/sub-01_bold.nii.gz'  # missing the required task entity


def test_validate_returns_the_findings_and_prints_them(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every finding is both returned to the caller and shown to the user."""
    build(tmp_path, BROKEN)
    issues = validate(FileTree.read_from_filesystem(str(tmp_path)), schema)

    assert len(issues) == 1
    assert issues.has_errors

    out = capsys.readouterr().out
    assert 'error: MISSING_REQUIRED_ENTITY: sub-01/func/sub-01_bold.nii.gz' in out
    assert 'missing required entities: task' in out
    assert '1 error(s), 0 warning(s)' in out


def test_validate_says_so_when_there_is_nothing_wrong(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean dataset gets a clear answer, not silence."""
    build(tmp_path, VALID)
    issues = validate(FileTree.read_from_filesystem(str(tmp_path)), schema)

    assert len(issues) == 0
    assert not issues.has_errors
    assert 'No filename problems found' in capsys.readouterr().out


def test_verbose_adds_the_schema_rule(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """``-v`` shows which rule produced the finding, so a user can check the standard."""
    build(tmp_path, BROKEN)
    tree = FileTree.read_from_filesystem(str(tmp_path))

    validate(tree, schema, verbose=False)
    assert 'rule:' not in capsys.readouterr().out

    validate(tree, schema, verbose=True)
    assert 'rule: rules.files.raw.func.func' in capsys.readouterr().out


def test_cli_exit_code_is_one_when_there_are_errors(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A CI job reads the exit code, not the printed text."""
    build(tmp_path, BROKEN)
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 1
    assert 'MISSING_REQUIRED_ENTITY' in result.stdout


def test_cli_exit_code_is_zero_on_a_clean_dataset(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """The converse: a good dataset must not fail the build."""
    build(tmp_path, VALID)
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0
    assert 'No filename problems found' in result.stdout


def test_cli_reports_exactly_what_the_module_reports(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """The CLI must not grow a second implementation of the checks.

    It once had its own tree walk and called ``is_bids`` per path, which could drift
    from the module's results. Now it delegates, and this test fails if anything is
    ever reported by one and not the other.
    """
    build(
        tmp_path,
        VALID,
        BROKEN,
        'sub-01/notes.txt',
        'sub-01/anat/sub-01_T1w.txt',
        'sub-02/anat/sub-01_T1w.nii.gz',
    )
    expected = {
        (i.code, i.location)
        for i in collect_filename_issues(FileTree.read_from_filesystem(str(tmp_path)), schema)
    }
    assert expected, 'the fixture should produce findings, otherwise this proves nothing'

    result = runner.invoke(app, [str(tmp_path)])

    reported = set()
    for line in result.stdout.splitlines():
        # "severity: CODE: location"
        parts = line.split(': ')
        if len(parts) == 3 and parts[0] in {s.value for s in Severity}:
            reported.add((parts[1], parts[2]))

    assert reported == expected
