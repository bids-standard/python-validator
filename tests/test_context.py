from bids_validator import context
from bids_validator.types.files import FileTree

import pytest

def test_load(examples, schema):
    tree = FileTree.read_from_filesystem(examples / 'synthetic')
    ds = context.Dataset(tree, schema)

    assert ds.dataset_description.Name.startswith('Synthetic dataset')
    assert ds.subjects.participant_id == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.subjects.sub_dirs) == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.datatypes) == ["anat", "beh", "func"]
    assert sorted(ds.modalities) == ["beh", "mri"]


@pytest.mark.parametrize(
        "depth, expected",
        [
            (2, {"anat", "beh", "func"}),
            (1, set())
        ])
def test_find_datatypes(examples, schema, depth, expected):
    tree = FileTree.read_from_filesystem(examples / 'synthetic')
    datatypes = schema.objects.datatypes

    result = context.find_datatypes(tree, datatypes, max_depth=depth)

    assert result == expected

def test_fileparts(examples, schema):
    tree = FileTree.read_from_filesystem(examples / 'synthetic')

    T1w = tree / 'sub-01' / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii'
    parts = context.FileParts.from_file(T1w, schema)
    assert parts == context.FileParts(
        path='/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii',
        stem='sub-01_ses-01_T1w',
        entities={'sub': '01', 'ses': '01'},
        datatype='anat',
        suffix='T1w',
        extension='.nii',
    )

def test_context(examples, schema):

    tree = FileTree.read_from_filesystem(examples / 'synthetic')
    ds = context.Dataset(tree, schema)
    T1w = tree / 'sub-01' / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii'

    file_context = context.Context(T1w, ds)

    assert file_context.schema == schema
    assert file_context.dataset == ds
    assert file_context.entiities == {'sub': '01', 'ses': '01'}
    assert file_context.path == '/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii'
    assert file_context.datatype == 'anat'
    assert file_context.suffix == 'T1w'
    assert file_context.extension == '.nii'
    assert file_context.modality == 'mri'
    assert file_context.size == 352

    ## Tests for:
    #  subject
    #  sidecar
    #  associations
    #  columns
    #  json
    #  gzip
    #  nifti_header
    #  ome
    #  tiff
