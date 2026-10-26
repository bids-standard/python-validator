"""Tests for the command line.

The CLI is a thin front end over :mod:`bids_validator.checks`. These tests cover the
part that is genuinely the CLI's own: what it prints, and what it exits with. The last
test is the important one. It pins the CLI to the module, so a second walk cannot
creep back into ``__main__``.
"""

import pathlib

import pytest
from bidsschematools.types.namespace import Namespace
from typer.testing import CliRunner

from bids_validator.__main__ import app, validate
from bids_validator.checks import collect_issues
from bids_validator.issues import Severity
from bids_validator.types.files import FileTree

from .helpers import clean_dataset

runner = CliRunner()

BROKEN = 'sub-01/notes.txt'  # not a BIDS name: exactly one finding, NOT_INCLUDED


def broken_dataset(root: pathlib.Path) -> pathlib.Path:
    """The clean dataset plus one file BIDS does not include."""
    clean_dataset(root)
    (root / BROKEN).write_text('notes')
    return root


def test_validate_returns_the_findings_and_prints_them(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every finding is both returned to the caller and shown to the user."""
    issues = validate(FileTree.read_from_filesystem(str(broken_dataset(tmp_path))), schema)

    assert len(issues) == 1
    assert issues.has_errors

    out = capsys.readouterr().out
    assert 'error: NOT_INCLUDED: sub-01/notes.txt' in out
    assert '1 error(s), 0 warning(s)' in out


def test_validate_says_so_when_there_is_nothing_wrong(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean dataset gets a clear answer, not silence."""
    issues = validate(FileTree.read_from_filesystem(str(clean_dataset(tmp_path))), schema)

    assert len(issues) == 0
    assert not issues.has_errors
    assert 'No problems found' in capsys.readouterr().out


def test_verbose_adds_the_schema_rule(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """``-v`` shows which rule produced the finding, so a user can check the standard."""
    clean_dataset(tmp_path)
    (tmp_path / 'README').write_text('short')
    tree = FileTree.read_from_filesystem(str(tmp_path))

    validate(tree, schema, verbose=False)
    assert 'rule:' not in capsys.readouterr().out

    validate(tree, schema, verbose=True)
    assert 'rule: rules.checks.general.ReadmeFileSmall' in capsys.readouterr().out


def test_a_dataset_level_finding_has_no_file(
    tmp_path: pathlib.Path, schema: Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    clean_dataset(tmp_path)
    (tmp_path / 'dataset_description.json').unlink()
    validate(FileTree.read_from_filesystem(str(tmp_path)), schema)
    assert 'error: MISSING_DATASET_DESCRIPTION: (dataset)' in capsys.readouterr().out


def test_cli_exit_code_is_one_when_there_are_errors(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A CI job reads the exit code, not the printed text."""
    result = runner.invoke(app, [str(broken_dataset(tmp_path))])
    assert result.exit_code == 1
    assert 'NOT_INCLUDED' in result.stdout


def test_cli_exit_code_is_zero_with_only_warnings(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Warnings are shown but do not fail the build."""
    clean_dataset(tmp_path)
    (tmp_path / 'README').write_text('short')
    result = runner.invoke(app, [str(tmp_path)])
    assert result.exit_code == 0
    assert 'README_FILE_SMALL' in result.stdout


def test_cli_exit_code_is_zero_on_a_clean_dataset(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    result = runner.invoke(app, [str(clean_dataset(tmp_path))])
    assert result.exit_code == 0
    assert 'No problems found' in result.stdout


def test_cli_reports_exactly_what_the_module_reports(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """The CLI must not grow a second implementation of the checks.

    It once had its own tree walk and called ``is_bids`` per path, which could drift
    from the module's results. Now it delegates, and this test fails if anything is
    ever reported by one and not the other.
    """
    broken_dataset(tmp_path)
    for relpath in ('sub-01/anat/sub-01_T1w.txt', 'sub-02/anat/sub-01_T1w.nii.gz'):
        (tmp_path / relpath).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relpath).write_bytes(b'')
    expected = {
        (i.code, i.location)
        for i in collect_issues(FileTree.read_from_filesystem(str(tmp_path)), schema)
    }
    assert len(expected) > 3, 'the fixture should produce findings, otherwise this proves nothing'

    result = runner.invoke(app, [str(tmp_path)])

    reported = set()
    for line in result.stdout.splitlines():
        # "severity: CODE: location"
        parts = line.split(': ')
        if len(parts) == 3 and parts[0] in {s.value for s in Severity}:
            reported.add((parts[1], parts[2]))

    assert reported == expected
