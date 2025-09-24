import pytest

from bidsschematools.types.context import Subject
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


def test_walkback(synthetic_dataset, schema):
    bold = (
        synthetic_dataset
        / 'sub-01'
        / 'ses-01'
        / 'func'
        / 'sub-01_ses-01_task-nback_run-01_bold.nii'
    )
    sidecars = list(context.walk_back(bold, inherit=True))
    assert len(sidecars) == 1
    assert sidecars[0] is synthetic_dataset / 'task-nback_bold.json'

def test_context(synthetic_dataset, schema):

    sub01 = synthetic_dataset / 'sub-01'
    T1w = sub01 / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii'
    
    subject = Subject(context.Sessions(sub01))
    ds = context.Dataset(synthetic_dataset, schema)
    file_context = context.Context(T1w, ds, subject)

    assert file_context.schema is schema
    assert file_context.dataset is ds
    assert file_context.entities == {'sub': '01', 'ses': '01'}
    assert file_context.path == '/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii'
    assert file_context.datatype == 'anat'
    assert file_context.suffix == 'T1w'
    assert file_context.extension == '.nii'
    assert file_context.modality == 'mri'
    assert file_context.size == 352
    assert isinstance(file_context.subject.sessions, context.Sessions)
    assert sorted(file_context.subject.sessions.ses_dirs) == ["ses-01", "ses-02"]
    assert sorted(file_context.subject.sessions.session_id) == ["ses-01", "ses-02"]
    assert file_context.sidecar is None

    ## Tests for:
    #  associations
    #  columns
    #  json
    #  gzip
    #  nifti_header
    #  ome
    #  tiff

def test_sidecar_inheritance(examples):
    """Test to ensure inheritance principle is executed correctly"""
    dataset = FileTree.read_from_filesystem(examples / 'qmri_mp2rage')
    file = dataset / "sub-1" / "anat"/"sub-1_inv-2_part-mag_MP2RAGE.nii"

    sidecar = context.load_sidecar(file)

    assert sidecar["FlipAngle"] == 7
    assert sidecar["InversionTime"] == 2.7
    assert sidecar["RepetitionTimePreparation"] == 5.5


def test_sessions(synthetic_dataset):
    sub01 = synthetic_dataset / 'sub-01'

    sessions = context.Sessions(sub01)

    assert sorted(sessions.ses_dirs) == ["ses-01", "ses-02"]
    assert sorted(sessions.session_id) == ["ses-01", "ses-02"]
