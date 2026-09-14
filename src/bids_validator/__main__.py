# ruff: noqa: D100
# ruff: noqa: D103

try:
    import typer
except ImportError:
    print('⚠️ CLI dependencies are not installed. Install "bids_validator[cli]"')
    raise SystemExit(1) from None

import sys
from typing import Annotated

from bidsschematools.schema import load_schema
from bidsschematools.types.namespace import Namespace

from bids_validator.filename_checks import collect_filename_issues
from bids_validator.issues import DatasetIssues, Severity
from bids_validator.types.files import FileTree

app = typer.Typer()


def validate(tree: FileTree, schema: Namespace, verbose: bool = False) -> DatasetIssues:
    """Check every filename in the dataset against the schema and report what is wrong.

    The walk, the rule matching and the findings all come from
    :func:`~bids_validator.filename_checks.collect_filename_issues`, so the CLI and
    any library caller run exactly the same checks.

    Parameters
    ----------
    tree : FileTree
        Full FileTree object to iterate over and check
    schema : Namespace
        Schema object to validate dataset against
    verbose : bool
        Also print the schema rule each finding came from

    Returns
    -------
    DatasetIssues
        Every finding, so the caller can set an exit code.

    """
    issues = collect_filename_issues(tree, schema)

    for issue in issues:
        print(f'{issue.severity.value}: {issue.code}: {issue.location}')
        if issue.message:
            print(f'    {issue.message}')
        if verbose and issue.rule:
            print(f'    rule: {issue.rule}')

    errors = len(issues.by_severity(Severity.ERROR))
    warnings = len(issues.by_severity(Severity.WARNING))
    if issues:
        print(f'\n{errors} error(s), {warnings} warning(s)')
    else:
        print('No filename problems found')

    return issues


def show_version() -> None:
    """Show bids-validator version."""
    from . import __version__

    print(f'bids-validator {__version__} (Python {sys.version.split()[0]})')


def version_callback(value: bool) -> None:
    """Run the callback for CLI version flag.

    Parameters
    ----------
    value : bool
        value received from --version flag

    Raises
    ------
    typer.Exit
        Exit without any errors

    """
    if value:
        show_version()
        raise typer.Exit()


@app.command()
def main(
    bids_path: str,
    schema_path: str | None = None,
    verbose: Annotated[bool, typer.Option('--verbose', '-v', help='Show verbose output')] = False,
    version: Annotated[
        bool,
        typer.Option(
            '--version',
            help='Show version',
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    if verbose:
        show_version()

    root_path = FileTree.read_from_filesystem(bids_path)

    schema = load_schema(schema_path)

    issues = validate(root_path, schema, verbose=verbose)

    # A validator is normally run from a script or CI job, so the outcome has to be
    # readable from the exit code, not only from the printed text.
    if issues.has_errors:
        raise typer.Exit(code=1)


if __name__ == '__main__':
    app()
