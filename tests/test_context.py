import json
from collections.abc import Generator
from pathlib import Path

import fsspec
import pytest
from bidsschematools.types.context import Subject
from bidsschematools.types.namespace import Namespace

from bids_validator import context
from bids_validator.types.files import FileTree


@pytest.fixture
def synthetic_dataset(examples: Path) -> FileTree:
    return FileTree.read_from_filesystem(examples / 'synthetic')


@pytest.fixture
def memfs() -> Generator[fsspec.AbstractFileSystem, None, None]:
    mem = fsspec.filesystem('memory')
    mem.store.clear()
    yield mem
    mem.store.clear()


def test_load(synthetic_dataset: FileTree, schema: Namespace) -> None:
    ds = context.Dataset(synthetic_dataset, schema)

    assert ds.dataset_description.Name.startswith('Synthetic dataset')
    assert ds.subjects.participant_id == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.subjects.sub_dirs) == [f'sub-{i:02d}' for i in range(1, 6)]
    assert sorted(ds.datatypes) == ['anat', 'beh', 'func']
    assert sorted(ds.modalities) == ['beh', 'mri']


@pytest.mark.parametrize(('depth', 'expected'), [(2, {'anat', 'beh', 'func'}), (1, set())])
def test_find_datatypes(
    synthetic_dataset: FileTree,
    schema: Namespace,
    depth: int,
    expected: set[str],
) -> None:
    datatypes = schema.objects.datatypes

    result = context.find_datatypes(synthetic_dataset, datatypes, max_depth=depth)

    assert result == expected


def test_fileparts(synthetic_dataset: FileTree, schema: Namespace) -> None:
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


def test_walkback(synthetic_dataset: FileTree) -> None:
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


def test_context(synthetic_dataset: FileTree, schema: Namespace) -> None:
    sub01 = synthetic_dataset / 'sub-01'
    T1w = sub01 / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii'
    bold = sub01 / 'ses-01' / 'func' / 'sub-01_ses-01_task-nback_run-01_bold.nii'
    stim = sub01 / 'ses-01' / 'func' / 'sub-01_ses-01_task-nback_run-01_stim.tsv.gz'
    events = synthetic_dataset / 'task-nback_events.tsv'

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
    assert T1w_context.subject is not None
    assert isinstance(T1w_context.subject.sessions, context.Sessions)
    assert sorted(T1w_context.subject.sessions.ses_dirs) == ['ses-01', 'ses-02']
    assert T1w_context.subject.sessions.session_id is not None
    assert sorted(T1w_context.subject.sessions.session_id) == ['ses-01', 'ses-02']
    assert T1w_context.sidecar is not None
    assert T1w_context.sidecar == {}
    assert T1w_context.json is None
    assert T1w_context.gzip is None

    bold_context = context.Context(bold, ds, subject)

    assert bold_context.sidecar is not None
    assert bold_context.sidecar.to_dict() == {'TaskName': 'N-Back', 'RepetitionTime': 2.5}
    assert bold_context.json is None
    assert bold_context.gzip is None
    assert bold_context.nifti_header is not None
    assert bold_context.nifti_header.voxel_sizes == (2.0, 2.0, 2.0, 2.5)

    events_context = context.Context(events, ds, subject=None)

    assert events_context.sidecar == Namespace()
    assert events_context.json is None
    assert events_context.gzip is None
    assert events_context.nifti_header is None
    assert isinstance(events_context.columns, context.FileContents)
    assert 'onset' in events_context.columns
    assert len(events_context.columns.onset) == 42

    stim_context = context.Context(stim, ds, subject)
    assert stim_context.sidecar is not None
    assert set(stim_context.sidecar) == {'SamplingFrequency', 'StartTime', 'Columns'}
    assert stim_context.gzip is not None
    assert stim_context.gzip.filename == stim.name.removesuffix('.gz')
    assert stim_context.gzip.timestamp != 0
    assert stim_context.gzip.comment == ''
    assert isinstance(stim_context.columns, context.FileContents)
    assert list(stim_context.columns.keys()) == stim_context.sidecar.Columns

    ## Tests for:
    #  associations
    #  ome
    #  tiff


def test_context_json(examples: Path, schema: Namespace) -> None:
    dataset = FileTree.read_from_filesystem(examples / 'qmri_vfa')
    file = dataset / 'sub-01' / 'anat' / 'sub-01_flip-1_VFA.json'

    ds = context.Dataset(dataset, schema)
    file_context = context.Context(file, ds, subject=None)

    assert file_context.json is not None
    assert file_context.json.to_dict() == {'FlipAngle': 3, 'RepetitionTimeExcitation': 0.0150}


def test_sidecar_inheritance(examples: Path) -> None:
    """Test to ensure inheritance principle is executed correctly"""
    dataset = FileTree.read_from_filesystem(examples / 'qmri_mp2rage')
    file = dataset / 'sub-1' / 'anat' / 'sub-1_inv-2_part-mag_MP2RAGE.nii'

    sidecar = context.load_sidecar(file)

    assert sidecar['FlipAngle'] == 7
    assert sidecar['InversionTime'] == 2.7
    assert sidecar['RepetitionTimePreparation'] == 5.5


def test_sidecar_order(memfs: fsspec.AbstractFileSystem) -> None:
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


def test_sessions(synthetic_dataset: FileTree) -> None:
    sub01 = synthetic_dataset / 'sub-01'

    sessions = context.Sessions(sub01)

    assert sorted(sessions.ses_dirs) == ['ses-01', 'ses-02']
    assert sessions.session_id is not None
    assert sorted(sessions.session_id) == ['ses-01', 'ses-02']


def test_load_tsv(synthetic_dataset: FileTree) -> None:
    tsv_file_tree = synthetic_dataset / 'participants.tsv'
    tsv_file = context.load_tsv(tsv_file_tree)

    data_set = {
        'participant_id': ('sub-01', 'sub-02', 'sub-03', 'sub-04', 'sub-05'),
        'age': (34, 38, 22, 21, 42),
        'sex': ('F', 'M', 'M', 'F', 'M'),
    }

    assert tsv_file.keys() == data_set.keys()
    assert [tsv_file[key] == data_set[key] for key in tsv_file]


def test_load_tsv_gz(synthetic_dataset: FileTree) -> None:
    headers = ('respiratory', 'cardiac')
    tsvgz_file_tree = (
        synthetic_dataset
        / 'sub-01'
        / 'ses-01'
        / 'func'
        / 'sub-01_ses-01_task-nback_run-01_stim.tsv.gz'
    )

    tsvgz_file = context.load_tsv_gz(tsvgz_file_tree, headers)

    assert tuple(tsvgz_file.keys()) == headers
    # Will need an additional test for the content


def test_load_gzip_header(synthetic_dataset: FileTree) -> None:
    tsvgz = (
        synthetic_dataset
        / 'sub-01'
        / 'ses-01'
        / 'func'
        / 'sub-01_ses-01_task-nback_run-01_stim.tsv.gz'
    )

    gz_header = context.load_gzip_header(tsvgz)
    assert gz_header is not None
    assert gz_header.timestamp != 0
    assert gz_header.filename == tsvgz.name.removesuffix('.gz')
    assert gz_header.comment == ''


def test_nifti_mrs_header(
    mrs_data: Path,
    schema: Namespace,
    memfs: fsspec.AbstractFileSystem,
    tmp_path: Path,
) -> None:
    example_01 = mrs_data / 'example_01.nii.gz'
    memfs.pipe(
        {
            '/dataset_description.json': json.dumps(
                {'Name': 'MRS Test Dataset', 'BIDSVersion': '1.10.1'}
            ).encode(),
            '/sub-01/mrs/sub-01_acq-press_mrs.nii.gz': example_01.read_bytes(),
        }
    )
    memfs.get('memory:///', str(tmp_path), recursive=True)
    dataset = FileTree.read_from_filesystem(tmp_path)
    sub01 = dataset / 'sub-01'
    mrs = dataset / 'sub-01' / 'mrs' / 'sub-01_acq-press_mrs.nii.gz'

    ds = context.Dataset(dataset, schema)
    subject = Subject(context.Sessions(sub01))
    mrs_context = context.Context(mrs, ds, subject)

    assert mrs_context.nifti_header is not None
    assert isinstance(mrs_context.nifti_header.mrs, Namespace)
    assert mrs_context.nifti_header.mrs.ResonantNucleus == ['1H']


@pytest.mark.parametrize(
    ('input_arg', 'expected_result'),
    [
        pytest.param('participants.tsv', 1, id='single input - present'),
        pytest.param('samples.tsv', 0, id='single input - absent'),
        pytest.param(
            ['README', 'README.md', 'README.rst', 'README.txt'], 1, id='list input - present'
        ),
    ],
)
def test_exists_dataset(
    synthetic_dataset: FileTree,
    schema: Namespace,
    input_arg: str | list[str],
    expected_result: int,
) -> None:
    dataset = context.Dataset(synthetic_dataset, schema)

    file = synthetic_dataset / 'participants.tsv'

    file_context = context.Context(file, dataset, None)

    assert file_context.exists(input_arg, 'dataset') == expected_result


def test_exists_stimuli(synthetic_dataset: FileTree, schema: Namespace) -> None:
    dataset = context.Dataset(synthetic_dataset, schema)

    file = synthetic_dataset / 'sub-01' / 'ses-01' / 'beh' / 'sub-01_ses-01_task-stroop_beh.tsv'

    file_context = context.Context(file, dataset, None)
    columns = file_context.columns
    assert columns is not None

    assert file_context.exists(columns.stim_file, 'stimuli') == len(columns.stim_file)
    assert file_context.exists('missing_file.jpg', 'stimuli') == 0


def test_exists_file(synthetic_dataset: FileTree, schema: Namespace) -> None:
    dataset = context.Dataset(synthetic_dataset, schema)

    file = synthetic_dataset / 'sub-01' / 'ses-01' / 'sub-01_ses-01_scans.tsv'

    file_context = context.Context(file, dataset, None)
    columns = file_context.columns
    assert columns is not None

    assert file_context.exists(columns.filename, 'file') == len(columns.filename)


@pytest.mark.parametrize(
    ('file_path', 'expected_result'),
    [
        (Path('sub-01') / 'ses-meg' / 'meg' / 'sub-01_ses-meg_coordsystem.json', 1),
        (Path('sub-01') / 'ses-mri' / 'fmap' / 'sub-01_ses-mri_phasediff.json', 9),
    ],
)
def test_exists_subject(
    examples: Path, schema: Namespace, file_path: Path, expected_result: int
) -> None:
    ds000117 = FileTree.read_from_filesystem(examples / 'ds000117')

    dataset = context.Dataset(ds000117, schema)

    file = ds000117 / file_path

    file_context = context.Context(file, dataset, None)
    assert file_context.json is not None

    assert file_context.exists(file_context.json.IntendedFor, 'subject') == expected_result


def test_exists_bidsuri(examples: Path, schema: Namespace) -> None:
    ds000246 = FileTree.read_from_filesystem(examples / 'ds000246')

    dataset = context.Dataset(ds000246, schema)

    file = ds000246 / 'sub-0001' / 'meg' / 'sub-0001_task-AEF_run-01_meg.json'

    file_context = context.Context(file, dataset, None)
    assert file_context.json is not None

    assert file_context.exists(file_context.json.AssociatedEmptyRoom, 'bids-uri') == 1


def _small_dataset(root: Path, *relpaths: str) -> FileTree:
    """Write a dataset_description.json, a README and the given empty files or folders."""
    (root / 'dataset_description.json').write_text('{"Name": "t", "BIDSVersion": "1.11.1"}')
    (root / 'README').write_text('A test dataset.')
    for relpath in relpaths:
        path = root / relpath
        if relpath.endswith('/'):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'')
    return FileTree.read_from_filesystem(root)


def test_find_datatypes_leaves_the_schema_alone(tmp_path: Path, schema: Namespace) -> None:
    """A folder name with a dot must not change the (cached, shared) schema.

    ``".git" in namespace`` reads the dot as a path separator and inserts an empty
    key into the Namespace. ``load_schema()`` returns the same object to every caller,
    so every context built afterwards failed with ``AttributeError: ... 'value'``.
    """
    tree = _small_dataset(tmp_path, '.git/', '.datalad/', 'sub-01/anat/sub-01_T1w.nii.gz')
    before = list(schema.objects.datatypes.keys())

    found = context.find_datatypes(tree, schema.objects.datatypes)

    assert found == {'anat'}
    assert list(schema.objects.datatypes.keys()) == before


def test_modalities_skips_datatypes_without_a_modality(tmp_path: Path, schema: Namespace) -> None:
    """``phenotype`` is a datatype that belongs to no modality; it used to raise KeyError."""
    tree = _small_dataset(tmp_path, 'phenotype/survey.tsv', 'sub-01/anat/sub-01_T1w.nii.gz')
    dataset = context.Dataset(tree, schema)

    assert set(dataset.datatypes) == {'anat', 'phenotype'}
    assert dataset.modalities == ['mri']


@pytest.mark.parametrize(
    ('arg', 'rule', 'expected'),
    [
        pytest.param('README', 'dataset', 1, id='relative'),
        # ``path`` in the context always starts with "/"; it means the dataset root.
        pytest.param('/README', 'dataset', 1, id='leading-slash-is-the-root'),
        pytest.param('/sub-01/anat/sub-01_T1w.nii.gz', 'dataset', 1, id='leading-slash-deep'),
        pytest.param('anat/sub-01_T1w.nii.gz', 'subject', 1, id='subject-relative'),
        # Not a path at all: not found, and no "Protocol not known: 'bids'" error.
        pytest.param('bids::README', 'dataset', 0, id='uri-given-to-dataset-rule'),
        pytest.param('bids::README', 'subject', 0, id='uri-given-to-subject-rule'),
        pytest.param('../README', 'dataset', 0, id='parent-is-never-found'),
        pytest.param('', 'dataset', 0, id='empty-path'),
    ],
)
def test_exists_resolves_paths_by_hand(
    tmp_path: Path, schema: Namespace, arg: str, rule: str, expected: int
) -> None:
    tree = _small_dataset(tmp_path, 'sub-01/anat/sub-01_T1w.nii.gz')
    file_context = context.Context(
        tree / 'sub-01' / 'anat' / 'sub-01_T1w.nii.gz', context.Dataset(tree, schema), None
    )

    assert file_context.exists(arg, rule) == expected


# --- reading file contents for the schema rules ------------------------------


def _ctx(root: Path, relpath: str, schema: Namespace) -> context.Context:
    tree = FileTree.read_from_filesystem(root)
    return context.Context(tree / relpath, context.Dataset(tree, schema), None)


def _files(root: Path, files: dict[str, object]) -> Path:
    (root / 'dataset_description.json').write_text('{"Name": "t", "BIDSVersion": "1.11.1"}')
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))
    return root


def test_a_json_file_has_no_sidecar(tmp_path: Path, schema: Namespace) -> None:
    _files(tmp_path, {'sub-01/anat/sub-01_T1w.json': {'EchoTime': 0.01}})
    assert _ctx(tmp_path, 'sub-01/anat/sub-01_T1w.json', schema).sidecar == {}


def test_repetition_time_is_rounded_to_milliseconds(tmp_path: Path, schema: Namespace) -> None:
    _files(
        tmp_path,
        {
            'sub-01/func/sub-01_task-x_bold.nii.gz': '',
            'task-x_bold.json': {'RepetitionTime': 2.00049},
        },
    )
    assert (
        _ctx(tmp_path, 'sub-01/func/sub-01_task-x_bold.nii.gz', schema).sidecar.RepetitionTime
        == 2.0
    )


def test_a_broken_sidecar_is_skipped_not_fatal(tmp_path: Path, schema: Namespace) -> None:
    """The broken JSON is reported on its own; the other levels still apply."""
    _files(
        tmp_path,
        {
            'sub-01/func/sub-01_task-x_bold.nii.gz': '',
            'task-x_bold.json': {'TaskName': 'x'},
            'sub-01/func/sub-01_task-x_bold.json': '{"broken": ',
        },
    )
    ctx = _ctx(tmp_path, 'sub-01/func/sub-01_task-x_bold.nii.gz', schema)
    assert ctx.sidecar == {'TaskName': 'x'}


def test_sidecar_origins_name_the_nearest_file(tmp_path: Path, schema: Namespace) -> None:
    _files(
        tmp_path,
        {
            'sub-01/func/sub-01_task-x_bold.nii.gz': '',
            'task-x_bold.json': {'TaskName': 'x', 'RepetitionTime': 2},
            'sub-01/func/sub-01_task-x_bold.json': {'RepetitionTime': 3},
        },
    )
    ctx = _ctx(tmp_path, 'sub-01/func/sub-01_task-x_bold.nii.gz', schema)
    assert ctx.sidecar_origins == {
        'RepetitionTime': 'sub-01/func/sub-01_task-x_bold.json',
        'TaskName': 'task-x_bold.json',
    }


@pytest.mark.parametrize(
    ('description', 'kind'),
    [
        ({'Name': 't', 'BIDSVersion': '1.11.1'}, 'raw'),
        ({'Name': 't', 'BIDSVersion': '1.11.1', 'GeneratedBy': [{'Name': 'x'}]}, 'derivative'),
        ({'Name': 't', 'BIDSVersion': '1.11.1', 'DatasetType': 'study'}, 'study'),
    ],
)
def test_dataset_type_defaults_like_the_reference(
    tmp_path: Path, schema: Namespace, description: dict[str, object], kind: str
) -> None:
    (tmp_path / 'dataset_description.json').write_text(json.dumps(description))
    dataset = context.Dataset(FileTree.read_from_filesystem(tmp_path), schema)
    assert dataset.dataset_description.DatasetType == kind


def test_a_missing_description_is_empty_not_an_error(tmp_path: Path, schema: Namespace) -> None:
    (tmp_path / 'README').write_text('x')
    dataset = context.Dataset(FileTree.read_from_filesystem(tmp_path), schema)
    assert dataset.dataset_description == {'DatasetType': 'raw'}


def test_a_record_keeps_dotted_keys() -> None:
    """A Namespace reads "key_resp.rt" as a path; a FileContents keeps it a key."""
    record = context.FileContents({'key_resp.rt': (0.5,), 'onset': (1,)})
    assert list(record) == ['key_resp.rt', 'onset']
    assert record['key_resp.rt'] == (0.5,)
    assert record.onset == (1,)
    with pytest.raises(AttributeError):
        _ = record.missing
