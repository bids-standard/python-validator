import json

import fsspec
import pytest
from bidsschematools.types.context import Subject

from bids_validator import context
from bids_validator.types.files import FileTree


@pytest.fixture
def synthetic_dataset(examples):
    return FileTree.read_from_filesystem(examples / 'synthetic')


@pytest.fixture
def memfs():
    mem = fsspec.filesystem('memory')
    mem.store.clear()
    yield mem
    mem.store.clear()


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
    bold = sub01 / 'ses-01' / 'func' / 'sub-01_ses-01_task-nback_run-01_bold.nii'

    subject = Subject(context.Sessions(sub01))
    ds = context.Dataset(synthetic_dataset, schema)
    T1w_context = context.Context(T1w, ds, subject)

    assert T1w_context.schema is schema
    assert T1w_context.dataset is ds
    assert T1w_context.entities == {'sub': '01', 'ses': '01'}
    assert T1w_context.path == '/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii'
    assert T1w_context.datatype == 'anat'
    assert T1w_context.suffix == 'T1w'
    assert T1w_context.extension == '.nii'
    assert T1w_context.modality == 'mri'
    assert T1w_context.size == 352
    assert isinstance(T1w_context.subject.sessions, context.Sessions)
    assert sorted(T1w_context.subject.sessions.ses_dirs) == ['ses-01', 'ses-02']
    assert sorted(T1w_context.subject.sessions.session_id) == ['ses-01', 'ses-02']
    assert T1w_context.sidecar == {}
    assert T1w_context.json is None

    bold_context = context.Context(bold, ds, subject)

    assert bold_context.sidecar.to_dict() == {'TaskName': 'N-Back', 'RepetitionTime': 2.5}
    assert bold_context.json is None

    ## Tests for:
    #  associations
    #  columns
    #  gzip
    #  nifti_header
    #  ome
    #  tiff


def test_context_json(examples, schema):
    dataset = FileTree.read_from_filesystem(examples / 'qmri_vfa')
    file = dataset / 'sub-01' / 'anat' / 'sub-01_flip-1_VFA.json'

    ds = context.Dataset(dataset, schema)
    file_context = context.Context(file, ds, subject=None)

    assert file_context.json.to_dict() == {'FlipAngle': 3, 'RepetitionTimeExcitation': 0.0150}


def test_sidecar_inheritance(examples):
    """Test to ensure inheritance principle is executed correctly"""
    dataset = FileTree.read_from_filesystem(examples / 'qmri_mp2rage')
    file = dataset / 'sub-1' / 'anat' / 'sub-1_inv-2_part-mag_MP2RAGE.nii'

    sidecar = context.load_sidecar(file)

    assert sidecar['FlipAngle'] == 7
    assert sidecar['InversionTime'] == 2.7
    assert sidecar['RepetitionTimePreparation'] == 5.5


def test_sidecar_order(memfs):
    """Test to ensure inheritance principle is skipped when inherit=False"""
    root_json = {'rootOverwriteA': 'root', 'rootOverwriteB': 'root', 'rootValue': 'root'}
    subject_json = {'rootOverwriteA': 'subject', 'subOverwrite': 'subject', 'subValue': 'subject'}
    anat_json = {'rootOverwriteB': 'anat', 'subOverwrite': 'anat', 'anatValue': 'anat'}
    memfs.pipe(
        {
            '/T1w.json': json.dumps(root_json).encode(),
            '/sub-01/sub-01_T1w.json': json.dumps(subject_json).encode(),
            '/sub-01/anat/sub-01_T1w.json': json.dumps(anat_json).encode(),
            '/sub-01/anat/sub-01_T1w.nii': b'',
        }
    )

    dataset = FileTree.read_from_filesystem('memory://')
    file = dataset / 'sub-01' / 'anat' / 'sub-01_T1w.nii'
    sidecar = context.load_sidecar(file)
    assert sidecar == {
        'rootValue': 'root',
        'subValue': 'subject',
        'rootOverwriteA': 'subject',
        'anatValue': 'anat',
        'rootOverwriteB': 'anat',
        'subOverwrite': 'anat',
    }


def test_sessions(synthetic_dataset):
    sub01 = synthetic_dataset / 'sub-01'

    sessions = context.Sessions(sub01)

    assert sorted(sessions.ses_dirs) == ['ses-01', 'ses-02']
    assert sorted(sessions.session_id) == ['ses-01', 'ses-02']


def test_load_tsv(synthetic_dataset):

    tsv_file_tree = synthetic_dataset / 'participants.tsv'
    tsv_file = context.load_tsv(tsv_file_tree)

    data_set = {
        "participant_id": ("sub-01", "sub-02", "sub-03", "sub-04", "sub-05"),
        "age": (34, 38, 22, 21, 42),
        "sex": ("F", "M", "M", "F", "M")
    }

    assert tsv_file.keys() == data_set.keys()
    assert [tsv_file[key] == data_set[key] for key in tsv_file.keys()]  


def test_load_tsv_gz(synthetic_dataset):

    headers = ("respiratory", "cardiac")
    tsvgz_file_tree = synthetic_dataset / "sub-01" / "ses-01" / "func" /"sub-01_ses-01_task-nback_run-01_stim.tsv.gz"

    tsvgz_file = context.load_tsv_gz(tsvgz_file_tree, headers)

    assert tuple(tsvgz_file.keys()) == headers
    # Will need an additional test for the content
