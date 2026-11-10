"""Tests for the checks that a file can be read at all."""

import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.checks.integrity import dataset_integrity_issues, integrity_issues
from bids_validator.context import Dataset
from bids_validator.types.files import FileTree

from ..helpers import build, findings, gzipped, nifti, write


def found(root: pathlib.Path, schema: Namespace) -> list[tuple[str, str]]:
    return findings(root, schema, integrity_issues)


@pytest.mark.parametrize(
    ('relpath', 'content', 'code'),
    [
        ('sub-01/anat/sub-01_T1w.json', b'', 'EMPTY_FILE'),
        ('sub-01/anat/sub-01_T1w.json', b'{"a": ', 'JSON_INVALID'),
        ('sub-01/anat/sub-01_T1w.json', b'\xef\xbb\xbf{}', 'INVALID_JSON_ENCODING'),  # a BOM
        ('sub-01/anat/sub-01_T1w.json', b'{"a": "\xff"}', 'INVALID_JSON_ENCODING'),
        ('sub-01/anat/sub-01_T1w.json', b'[1, 2]', 'JSON_NOT_AN_OBJECT'),
        ('sub-01/anat/sub-01_T1w.nii.gz', b'not an image', 'NIFTI_HEADER_UNREADABLE'),
        ('participants.tsv', b'participant_id\tage\tage\n', 'TSV_COLUMN_HEADER_DUPLICATE'),
        ('participants.tsv', b'participant_id\nsub-01\n\nsub-02\n', 'TSV_EMPTY_LINE'),
        ('participants.tsv', b'participant_id\tage\nsub-01\n', 'TSV_EQUAL_ROWS'),
    ],
)
def test_each_code_fires(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str, content: bytes, code: str
) -> None:
    write(tmp_path, {relpath: content})
    assert (code, relpath) in found(tmp_path, schema)


def test_an_empty_image_is_empty_and_unreadable(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """Both, as the reference validator reports."""
    build(tmp_path, 'sub-01/anat/sub-01_T1w.nii.gz')
    result = found(tmp_path, schema)
    assert ('EMPTY_FILE', 'sub-01/anat/sub-01_T1w.nii.gz') in result
    assert ('NIFTI_HEADER_UNREADABLE', 'sub-01/anat/sub-01_T1w.nii.gz') in result


@pytest.mark.parametrize(
    ('relpath', 'content'),
    [
        ('sub-01/anat/sub-01_T1w.nii.gz', nifti((2, 2, 2))),
        ('sub-01/anat/sub-01_T1w.json', b'{"a": 1}'),
        ('participants.tsv', b'participant_id\nsub-01\n'),  # ends with a newline
        ('participants.tsv', b'\xef\xbb\xbfparticipant_id\r\nsub-01\r\n'),  # BOM, CRLF
        ('participants.tsv', b'participant_id\tage\n'),  # a header and no rows
    ],
)
def test_readable_files_are_quiet(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str, content: bytes
) -> None:
    write(tmp_path, {relpath: content})
    assert found(tmp_path, schema) == []


def test_a_gzipped_table_that_is_not_gzip(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """A headerless ``.tsv.gz`` takes its columns from the sidecar, then must decompress."""
    write(
        tmp_path,
        {
            'sub-01/func/sub-01_task-rest_physio.json': {'Columns': ['cardiac']},
            'sub-01/func/sub-01_task-rest_physio.tsv.gz': b'plain text, not gzip',
        },
    )
    assert ('INVALID_GZIP', 'sub-01/func/sub-01_task-rest_physio.tsv.gz') in found(
        tmp_path, schema
    )


def test_a_gzipped_table_with_the_wrong_number_of_cells(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    write(
        tmp_path,
        {
            'sub-01/func/sub-01_task-rest_physio.json': {'Columns': ['cardiac', 'respiratory']},
            'sub-01/func/sub-01_task-rest_physio.tsv.gz': gzipped('1\t2\n3\n'),
        },
    )
    assert ('TSV_EQUAL_ROWS', 'sub-01/func/sub-01_task-rest_physio.tsv.gz') in found(
        tmp_path, schema
    )


def test_two_equally_good_sidecars_are_ambiguous(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Reported on the first candidate, as in the reference."""
    write(
        tmp_path,
        {
            'sub-01/anat/sub-01_T1w.nii.gz': nifti((2, 2, 2)),
            'sub-01/anat/sub-01_acq-a_T1w.json': {},
            'sub-01/anat/sub-01_run-1_T1w.json': {},
            'sub-01/anat/sub-01_acq-a_run-1_T1w.nii.gz': nifti((2, 2, 2)),
        },
    )
    codes = found(tmp_path, schema)
    assert ('MULTIPLE_INHERITABLE_FILES', 'sub-01/anat/sub-01_acq-a_T1w.json') in codes


def test_an_exact_sidecar_wins_over_partial_ones(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Several candidates, one with every entity of the image: not ambiguous."""
    write(
        tmp_path,
        {
            'sub-01/anat/sub-01_acq-a_run-1_T1w.nii.gz': nifti((2, 2, 2)),
            'sub-01/anat/sub-01_acq-a_run-1_T1w.json': {},
            'sub-01/anat/sub-01_acq-a_T1w.json': {},
            'sub-01/anat/sub-01_run-1_T1w.json': {},
        },
    )
    assert not [c for c in found(tmp_path, schema) if c[0] == 'MULTIPLE_INHERITABLE_FILES']


def test_a_missing_dataset_description(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'README')
    (tmp_path / 'dataset_description.json').unlink()
    dataset = Dataset(FileTree.read_from_filesystem(str(tmp_path)), schema)
    [issue] = dataset_integrity_issues(dataset)
    assert issue.code == 'MISSING_DATASET_DESCRIPTION'
    assert issue.location is None


def test_a_present_dataset_description(tmp_path: pathlib.Path, schema: Namespace) -> None:
    dataset = Dataset(FileTree.read_from_filesystem(str(build(tmp_path))), schema)
    assert dataset_integrity_issues(dataset) == []
