try:
    import typer
except ImportError:
    print('⚠️ CLI dependencies are not installed. Install "bids_validator[cli]"')
    raise SystemExit(1) from None

import sys
from typing_extensions import Annotated
import importlib.metadata

from bids_validator import BIDSValidator
from bids_validator.types.files import FileTree

__version__ = importlib.metadata.version(__package__ or __name__)
app = typer.Typer()


def walk(tree: FileTree):
    """Iterate over children of a FileTree and check if they are a directory or file.

    If it's a directory then run again recursively, if it's a file file check the file name is
    BIDS compliant.

    Parameters
    ----------
    tree : FileTree
        FileTree object to iterate over

    """
    for child in tree.children.values():
        if child.is_dir:
            yield from walk(child)
        else:
            yield child

def validate(tree: FileTree):
    """Check if the file path is BIDS compliant.

    Parameters
    ----------
    tree : FileTree
        Full FileTree object to iterate over and check

    """
    validator = BIDSValidator()

    for file in walk(tree):
        # The output of the FileTree.relative_path method always drops the initial for the path which
        # makes it fail the validator.is_bids check. Not sure if it's a Windows specific thing.
        # This line adds it back.
        path = f'/{file.relative_path}'

        if not validator.is_bids(path):
            print(f'{path} is not a valid bids filename')

def show_version():
    """Show bids-validator version
    """
    print(f'bids-validator {__version__} (Python {sys.version.split()[0]})')

@app.command()
def main(
    bids_path: str,
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v",
        help="Show verbose output"
    )] = False,
) -> None:
    
    if verbose: show_version()

    root_path = FileTree.read_from_filesystem(bids_path)

    validate(root_path)


if __name__ == '__main__':
    app()
