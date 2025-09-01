from bids_validator import context
from bids_validator.types.files import FileTree


def test_load(examples):
    tree = FileTree.read_from_filesystem(examples / 'synthetic')
    ds = context.Dataset(tree)

    assert ds.dataset_description.Name.startswith('Synthetic dataset')
    assert ds.subjects.participant_id == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.subjects.sub_dirs) == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.datatypes) == ["anat", "beh", "func"]
    assert sorted(ds.modalities) == ["beh", "mri"]

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
