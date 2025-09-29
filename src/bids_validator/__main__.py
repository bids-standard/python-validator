# ruff: noqa: D100
# ruff: noqa: D103

try:
    import typer
except ImportError:
    print('⚠️ CLI dependencies are not installed. Install "bids_validator[cli]"')
    raise SystemExit(1) from None

import sys
from collections.abc import Iterator
from typing import Annotated

from bidsschematools.schema import load_schema
from bidsschematools.types import Namespace
from bidsschematools.types.context import Subject

from bids_validator import BIDSValidator
from bids_validator.context import Context, Dataset, Sessions
from bids_validator.types.files import FileTree

app = typer.Typer()


def is_subject_dir(tree):
    return tree.name.startswith('sub-')


def walk(tree: FileTree, dataset: Dataset, subject: Subject = None) -> Iterator[Context]:
    """Iterate over children of a FileTree and check if they are a directory or file.

    If it's a directory then run again recursively, if it's a file file check the file name is
    BIDS compliant.

    Parameters
    ----------
    tree : FileTree
        FileTree object to iterate over
    dataset: Dataset
        Object containing properties for entire dataset
    subject: Subject
        object containing subject and session info

    """
    if subject is None and is_subject_dir(tree):
        subject = Subject(Sessions(tree))

    for child in tree.children.values():
        if child.is_dir:
            yield from walk(child, dataset, subject)
        else:
            yield Context(child, dataset, subject)


def validate(tree: FileTree, schema: Namespace):
    """Check if the file path is BIDS compliant.

    Parameters
    ----------
    tree : FileTree
        Full FileTree object to iterate over and check
    schema : Namespace
        Schema object to validate dataset against

    """
    validator = BIDSValidator()
    dataset = Dataset(tree, schema)

    for file in walk(tree, dataset):
        if not validator.is_bids(file.path):
            print(f'{file.path} is not a valid bids filename')


def show_version():
    """Show bids-validator version."""
    from . import __version__

    print(f'bids-validator {__version__} (Python {sys.version.split()[0]})')


def version_callback(value: bool):
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

    validate(root_path, schema)


if __name__ == '__main__':
    app()
