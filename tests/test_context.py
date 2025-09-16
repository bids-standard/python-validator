import pytest

from bids_validator import context
from bids_validator.types.files import FileTree


@pytest.fixture
def synthetic_dataset(examples):
    return FileTree.read_from_filesystem(examples / 'synthetic')


def test_load(synthetic_dataset, schema):
    ds = context.Dataset(synthetic_dataset, schema)

    assert ds.dataset_description.Name.startswith('Synthetic dataset')
    assert ds.subjects.participant_id == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.subjects.sub_dirs) == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.datatypes) == ['anat', 'beh', 'func']
    assert sorted(ds.modalities) == ['beh', 'mri']


@pytest.mark.parametrize(('depth', 'expected'), [(2, {'anat', 'beh', 'func'}), (1, set())])
def test_find_datatypes(synthetic_dataset, schema, depth, expected):
    datatypes = schema.objects.datatypes

    result = context.find_datatypes(synthetic_dataset, datatypes, max_depth=depth)

    assert result == expected


def test_fileparts(synthetic_dataset, schema):
    T1w = synthetic_dataset / 'sub-01' / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii'
    parts = context.FileParts.from_file(T1w, schema)
    assert parts == context.FileParts(
        path='/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii',
        stem='sub-01_ses-01_T1w',
        entities={'sub': '01', 'ses': '01'},
        datatype='anat',
        suffix='T1w',
        extension='.nii',
    )
