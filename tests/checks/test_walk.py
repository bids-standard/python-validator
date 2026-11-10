"""Tests for which files and folders a validation visits."""

import json
import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.checks.walk import DEFAULT_IGNORES, is_plain_folder, iter_contexts
from bids_validator.context import Dataset
from bids_validator.types.files import FileTree

from ..helpers import build


def visited(root: pathlib.Path, schema: Namespace) -> list[str]:
    """The relative path of every context the walk yields, in order."""
    tree = FileTree.read_from_filesystem(str(root))
    return [context.file.relative_path for context in iter_contexts(Dataset(tree, schema))]


def test_files_and_folders_are_visited_files_first(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Each folder's files come before its subfolders, as in the reference."""
    build(tmp_path, 'README', 'sub-01/anat/sub-01_T1w.nii.gz')
    paths = visited(tmp_path, schema)
    assert paths.index('README') < paths.index('sub-01/')
    assert paths.index('sub-01/') < paths.index('sub-01/anat/')
    assert paths.index('sub-01/anat/') < paths.index('sub-01/anat/sub-01_T1w.nii.gz')


@pytest.mark.parametrize(
    ('relpath', 'is_visited'),
    [
        ('code/run.py', False),  # the reference's top-level ignores
        ('sourcedata/raw.dcm', False),
        ('stimuli/face.png', False),
        ('log/run.txt', False),
        ('doc/notes.md', False),
        ('derivatives/x/file.txt', False),
        ('sub-01/log/run.txt', True),  # anchored at the root: deeper ones are checked
        ('sub-01/code/run.py', True),
        ('.DS_Store', False),  # hidden files at every level
        ('sub-01/.DS_Store', False),
        ('.git/config', False),
    ],
)
def test_ignores(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str, is_visited: bool
) -> None:
    build(tmp_path, relpath)
    assert (relpath in visited(tmp_path, schema)) is is_visited


def test_default_ignores_are_the_reference_list() -> None:
    assert DEFAULT_IGNORES == (
        '/sourcedata/',
        '/derivatives/',
        '/code/',
        '/stimuli/',
        '/log/',
        '/doc/',
    )


def test_bidsignore_is_visited_and_applied(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'extras/notes.txt')
    (tmp_path / '.bidsignore').write_text('extras/\n')
    paths = visited(tmp_path, schema)
    assert '.bidsignore' in paths
    assert 'extras/' not in paths
    assert 'extras/notes.txt' not in paths


def test_a_directory_recording_is_one_unit(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/meg/sub-01_task-rest_meg.ds/BadChannels')
    paths = visited(tmp_path, schema)
    assert 'sub-01/meg/sub-01_task-rest_meg.ds/' in paths
    assert 'sub-01/meg/sub-01_task-rest_meg.ds/BadChannels' not in paths


def test_a_folder_named_like_a_file_is_one_unit(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """The schema's bare ``/`` extension: ``x-1_y/`` is a file-like folder, not walked."""
    build(tmp_path, 'sub-01/log/20200910-165242_a0c5/fmriprep.toml')
    paths = visited(tmp_path, schema)
    assert 'sub-01/log/20200910-165242_a0c5/' in paths
    assert 'sub-01/log/20200910-165242_a0c5/fmriprep.toml' not in paths


def test_an_ordinary_folder_with_a_recording_extension_is_walked(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """``old.ds`` has no entities, so it is just a folder."""
    build(tmp_path, 'sub-01/meg/old.ds/file.txt')
    assert 'sub-01/meg/old.ds/file.txt' in visited(tmp_path, schema)


def test_opaque_folders_are_visited_but_not_walked(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """``logs`` and ``docs`` are opaque in ``rules.directories``."""
    build(tmp_path, 'logs/run.txt', 'docs/guide.md')
    paths = visited(tmp_path, schema)
    assert 'logs/' in paths
    assert 'docs/' in paths
    assert 'logs/run.txt' not in paths
    assert 'docs/guide.md' not in paths


def test_a_raw_dataset_skips_nested_derivatives(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/derivatives/x.txt')
    paths = visited(tmp_path, schema)
    assert 'sub-01/derivatives/' not in paths
    assert 'sub-01/derivatives/x.txt' not in paths


def test_a_derivative_dataset_walks_its_own_folders(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    build(tmp_path, 'sub-01/anat/sub-01_desc-x_T1w.nii.gz')
    (tmp_path / 'dataset_description.json').write_text(
        json.dumps({'Name': 'd', 'BIDSVersion': '1.11.1', 'DatasetType': 'derivative'})
    )
    assert 'sub-01/anat/sub-01_desc-x_T1w.nii.gz' in visited(tmp_path, schema)


def test_is_plain_folder_tells_folders_from_recordings(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    build(tmp_path, 'sub-01/meg/sub-01_task-rest_meg.ds/BadChannels')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    contexts = {c.file.relative_path: c for c in iter_contexts(Dataset(tree, schema))}
    assert is_plain_folder(contexts['sub-01/meg/'])
    assert not is_plain_folder(contexts['sub-01/meg/sub-01_task-rest_meg.ds/'])
    assert not is_plain_folder(contexts['dataset_description.json'])


def test_each_context_knows_its_subject(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/ses-1/anat/sub-01_ses-1_T1w.nii.gz')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    contexts = {c.file.relative_path: c for c in iter_contexts(Dataset(tree, schema))}
    image = contexts['sub-01/ses-1/anat/sub-01_ses-1_T1w.nii.gz']
    assert image.subject is not None
    assert image.subject.sessions.ses_dirs == ['ses-1']
    assert contexts['dataset_description.json'].subject is None
