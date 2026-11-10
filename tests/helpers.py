"""Helpers shared by the check tests: small datasets written to a temporary folder."""

import gzip
import io
import json
import pathlib
from collections.abc import Callable, Iterable, Mapping

import nibabel as nb
import numpy as np
from bidsschematools.types.namespace import Namespace

from bids_validator.checks import FOLDER_CHECKS, collect_issues
from bids_validator.context import Context
from bids_validator.issues import Issue
from bids_validator.types.files import FileTree

DESCRIPTION = {'Name': 'test', 'BIDSVersion': '1.11.1'}

# Every field rules.dataset_metadata asks for, so dataset_description.json is clean.
FULL_DESCRIPTION = {
    'Name': 'Clean',
    'BIDSVersion': '1.11.1',
    'DatasetType': 'raw',
    'License': 'CC0',
    'Authors': ['Ada Lovelace', 'Alan Turing'],
    'Acknowledgements': 'Thanks.',
    'HowToAcknowledge': 'Cite this.',
    'Funding': ['A grant'],
    'EthicsApprovals': ['An approval'],
    'ReferencesAndLinks': ['https://example.org'],
    'DatasetDOI': 'doi:10.0000/clean',
    'HEDVersion': '8.2.0',
    'GeneratedBy': [{'Name': 'hand'}],
    'SourceDatasets': [{'URL': 'https://example.org'}],
}

LONG_README = 'A dataset written for the tests. ' * 10  # over 150 bytes


def build(root: pathlib.Path, *relpaths: str) -> pathlib.Path:
    """Create a minimal dataset holding the given EMPTY files."""
    return write(root, dict.fromkeys(relpaths, b''))


def write(
    root: pathlib.Path,
    files: Mapping[str, str | bytes | dict[str, object]],
    *,
    description: Mapping[str, object] = DESCRIPTION,
) -> pathlib.Path:
    """Create a dataset from ``{relative path: content}``.

    Content is text, bytes, or a dict written as JSON. ``dataset_description.json``
    is written from ``description`` unless ``files`` names it. A path ending in ``/``
    is created as an empty folder.
    """
    root.mkdir(parents=True, exist_ok=True)
    if 'dataset_description.json' not in files:
        (root / 'dataset_description.json').write_text(json.dumps(description))
    for relpath, content in files.items():
        path = root / relpath
        if relpath.endswith('/'):
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            path.write_text(json.dumps(content))
        elif isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
    return root


def clean_dataset(root: pathlib.Path) -> pathlib.Path:
    """Write a small dataset that every check, ours and the reference's, finds clean."""
    return write(
        root,
        {
            'README': LONG_README,
            'participants.tsv': 'participant_id\nsub-01\n',
            'sub-01/beh/sub-01_task-rest_beh.tsv': 'response_time\n0.5\n',
            'task-rest_beh.json': {
                'TaskName': 'rest',
                'Instructions': 'Rest.',
                'TaskDescription': 'Resting.',
                'CogAtlasID': 'https://www.cognitiveatlas.org/task/id/trm_4c8a834779883',
                'CogPOID': 'http://www.cogpo.org/ontologies/CogPOver1.owl#COGPO_00000',
                'InstitutionName': 'A university',
                'InstitutionAddress': 'A street',
                'InstitutionalDepartmentName': 'A department',
                'response_time': {'Description': 'Response time', 'Units': 's'},
            },
        },
        description=FULL_DESCRIPTION,
    )


def nifti(shape: tuple[int, ...], zooms: tuple[float, ...] | None = None) -> bytes:
    """Return the bytes of a real, gzipped NIfTI-1 image of ``shape``."""
    image = nb.Nifti1Image(np.zeros(shape, dtype=np.uint8), np.eye(4))  # type: ignore[no-untyped-call]
    if zooms is not None:
        image.header.set_zooms(zooms)  # type: ignore[no-untyped-call]
    image.header.set_xyzt_units('mm', 'sec')  # type: ignore[no-untyped-call]
    return gzip.compress(image.to_bytes(), mtime=0)


def gzipped(text: str, *, mtime: int = 0, filename: str | None = None) -> bytes:
    """Return ``text`` gzipped, with a chosen header modification time and file name."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename=filename or '', mode='wb', fileobj=buffer, mtime=mtime) as fobj:
        fobj.write(text.encode())
    return buffer.getvalue()


def issues_of(
    root: pathlib.Path, schema: Namespace, *checks: Callable[[Context], list[Issue]]
) -> list[Issue]:
    """Return every finding of the given checks, or of all of them.

    A folder check (``folder_issues``) is run on folders, any other check on files.
    """
    tree = FileTree.read_from_filesystem(str(root))
    if not checks:
        return list(collect_issues(tree, schema))
    issues: Iterable[Issue] = collect_issues(
        tree,
        schema,
        dataset_checks=(),
        folder_checks=[check for check in checks if check in FOLDER_CHECKS],
        file_checks=[check for check in checks if check not in FOLDER_CHECKS],
    )
    return list(issues)


def findings(
    root: pathlib.Path,
    schema: Namespace,
    *checks: Callable[[Context], list[Issue]],
) -> list[tuple[str, str]]:
    """Return ``(code, location)`` of every finding, from the given checks or all of them."""
    return [(issue.code, issue.location or '') for issue in issues_of(root, schema, *checks)]


def codes(
    root: pathlib.Path, schema: Namespace, *checks: Callable[[Context], list[Issue]]
) -> dict[str, list[str]]:
    """Map each code found to the locations it was found at."""
    out: dict[str, list[str]] = {}
    for code, location in findings(root, schema, *checks):
        out.setdefault(code, []).append(location)
    return out
