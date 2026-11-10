# ruff: noqa: D100
# ruff: noqa: D103
# (The two lines above tell the linter not to ask for a docstring on this module, D100,
# or on its functions, D103. This file is what runs for ``bids-validator <dataset>``.)

# typer is an optional dependency (``pip install bids_validator[cli]``): the library can
# be used without it, so its absence is reported in a sentence, not a traceback.
try:
    import typer
except ImportError:
    print('⚠️ CLI dependencies are not installed. Install "bids_validator[cli]"')
    raise SystemExit(1) from None

import sys
from typing import Annotated

from bidsschematools.schema import load_schema
from bidsschematools.types.namespace import Namespace

from bids_validator.checks import collect_issues
from bids_validator.issues import DatasetIssues, Severity
from bids_validator.types.files import FileTree

# The command-line application. ``@app.command()`` below turns ``main``'s parameters into
# the command's arguments and options; ``app()`` at the bottom runs it.
app = typer.Typer()


def validate(tree: FileTree, schema: Namespace, verbose: bool = False) -> DatasetIssues:
    """Run every check on the dataset and report what is wrong.

    The walk and every check come from :func:`~bids_validator.checks.collect_issues`
    (reading, inheritance, names and places, the schema's rules), so the CLI and any
    library caller run exactly the same checks.

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
    issues = collect_issues(tree, schema)

    for issue in issues:
        print(f'{issue.severity.value}: {issue.code}: {issue.location or "(dataset)"}')
        if issue.message:
            print(f'    {issue.message}')
        if verbose and issue.rule:
            print(f'    rule: {issue.rule}')

    errors = len(issues.by_severity(Severity.ERROR))
    warnings = len(issues.by_severity(Severity.WARNING))
    if issues:
        print(f'\n{errors} error(s), {warnings} warning(s)')
    else:
        print('No problems found')

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


# ``@app.command()`` registers ``main`` as the command. typer reads its parameters:
# ``bids_path`` (no default) becomes the required argument, ``schema_path`` the option
# ``--schema-path``, and ``Annotated[bool, typer.Option(...)]`` attaches the flag names and
# help text to ``verbose`` and ``version``. ``is_eager`` runs ``--version`` before anything
# else, and its callback exits.
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


# True only when the file is run as a program (``python -m bids_validator``), not when it
# is imported by a test.
if __name__ == '__main__':
    app()
