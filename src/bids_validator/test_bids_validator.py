"""Test BIDSValidator functionality.

git-annex and datalad are used to download a test data structure without the
actual file contents.

"""

import os

import datalad.api
import pytest

from bids_validator import BIDSValidator

HOME = os.path.expanduser('~')

TEST_DATA_DICT = {
    'eeg_matchingpennies': ('https://gin.g-node.org/sappelhoff/eeg_matchingpennies'),
}

EXCLUDE_KEYWORDS = ['git', 'datalad', 'sourcedata', 'bidsignore']


def _download_test_data(test_data_dict, dsname):
    """Download test data using datalad."""
    url = test_data_dict[dsname]
    dspath = os.path.join(HOME, dsname)
    datalad.api.clone(source=url, path=dspath)
    return dspath


def _gather_test_files(dspath, exclude_keywords):
    """Get test files from dataset path, relative to dataset."""
    files = []
    for r, _, f in os.walk(dspath):
        for file in f:
            fname = os.path.join(r, file)
            fname = fname.replace(dspath, '')
            if not any(keyword in fname for keyword in exclude_keywords):
                files.append(fname)

    return files


dspath = _download_test_data(TEST_DATA_DICT, 'eeg_matchingpennies')
files = _gather_test_files(dspath, EXCLUDE_KEYWORDS)


@pytest.fixture(scope='module')
def validator():
    """Return a BIDSValidator instance."""
    validator = BIDSValidator()
    return validator


@pytest.mark.parametrize('fname', files)
def test_datasets(validator, fname):
    """Test that is_bids returns true for each file in a valid BIDS dataset."""
    assert validator.is_bids(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/T1w.json',
        '/dataset_description.json',
        '/README',
        '/README.md',
        '/README.rst',
        '/CHANGES',
        '/participants.tsv',
        '/participants.json',
    ],
)
def test_is_top_level(validator, fname):
    """Test that is_top_level returns true for top-level files."""
    assert validator.is_bids(fname)
    assert validator.is_top_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/anat/sub-01_T1w.nii.gz',
        '/RADME',  # typo
        '/CANGES',  # typo
    ],
)
def test_is_not_top_level(validator, fname):
    """Test that is_top_level returns false for non top-level files."""
    assert not validator.is_top_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/code/',
        '/derivatives/',
        '/sourcedata/',
        '/stimuli/',
        '/sourcedata/unstructured_data.nii.gz',
        '/sourcedata/dicom_dir/xyz.dcm',
        '/code/my_analysis/analysis.py',
        '/derivatives/preproc/sub-01/anat/sub-01_desc-preproc_T1w.nii.gz',
        '/stimuli/pic.jpg',
    ],
)
def test_is_associated_data(validator, fname):
    """Test that is_associated_data returns true for associated data."""
    assert validator.is_bids(fname)
    assert validator.is_associated_data(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/anat/sub-01_T1w.nii.gz',
        '/CODE/',
        '/derivatves/',
        '/source/',
        '/stimli/',
        '/.git/',
    ],
)
def test_is_not_associated_data(validator, fname):
    """Test that is_associated_data returns false for associated data."""
    assert not validator.is_associated_data(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/ses-1/sub-01_ses-1_scans.tsv',
        '/sub-01/ses-1/sub-01_ses-1_scans.json',
        '/sub-01/sub-01_scans.tsv',
        '/sub-01/sub-01_scans.json',
        '/sub-01/ses-1/sub-01_ses-1_task-rest_bold.json',
        '/sub-01/sub-01_task-rest_bold.json',
        '/sub-01/ses-1/sub-01_ses-1_asl.json',
        '/sub-01/sub-01_asl.json',
        '/sub-01/ses-1/sub-01_ses-1_pet.json',
        '/sub-01/sub-01_pet.json',
        '/sub-01/ses-1/sub-01_ses-1_proc-test_channels.tsv',
        '/sub-01/ses-1/sub-01_ses-1_channels.json',
        '/sub-01/sub-01_proc-test_channels.tsv',
        '/sub-01/sub-01_channels.json',
        '/sub-01/ses-1/sub-01_ses-1_space-CapTrak_electrodes.tsv',
        '/sub-01/ses-1/sub-01_ses-1_coordsystem.json',
        '/sub-01/sub-01_space-CapTrak_electrodes.tsv',
        '/sub-01/sub-01_coordsystem.json',
        '/sub-01/ses-1/sub-01_ses-1_motion.json',
        '/sub-01/sub-01_motion.json',
        '/sub-01/ses-1/sub-01_ses-1_TEM.json',
        '/sub-01/sub-01_TEM.json',
        '/sub-01/ses-1/sub-01_ses-1_nirs.json',
        '/sub-01/sub-01_nirs.json',
        '/sub-01/sub-01_dwi.bval',
        '/sub-01/sub-01_dwi.bvec',
        '/sub-01/sub-01_dwi.json',
        '/sub-01/sub-01_run-01_dwi.bval',
        '/sub-01/sub-01_run-01_dwi.bvec',
        '/sub-01/sub-01_run-01_dwi.json',
        '/sub-01/sub-01_acq-singleband_dwi.bval',
        '/sub-01/sub-01_acq-singleband_dwi.bvec',
        '/sub-01/sub-01_acq-singleband_dwi.json',
        '/sub-01/sub-01_acq-singleband_run-01_dwi.bval',
        '/sub-01/sub-01_acq-singleband_run-01_dwi.bvec',
        '/sub-01/sub-01_acq-singleband_run-01_dwi.json',
        '/sub-01/ses-test/sub-01_ses-test_dwi.bval',
        '/sub-01/ses-test/sub-01_ses-test_dwi.bvec',
        '/sub-01/ses-test/sub-01_ses-test_dwi.json',
        '/sub-01/ses-test/sub-01_ses-test_run-01_dwi.bval',
        '/sub-01/ses-test/sub-01_ses-test_run-01_dwi.bvec',
        '/sub-01/ses-test/sub-01_ses-test_run-01_dwi.json',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.bval',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.bvec',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.json',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.bval',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.bvec',
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.json',
    ],
)
def test_is_session_level(validator, fname):
    """Test that is_session_level returns true for session level files."""
    assert validator.is_bids(fname)
    assert validator.is_session_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        # Mismatch sessions
        '/sub-01/sub-01_ses-1_scans.tsv',
        '/sub-01/sub-01_ses-1_scans.json',
        '/sub-01/ses-1/sub-01_ses-2_scans.tsv',
        # File-level
        '/sub-01/ses-1/func/sub-01_ses-1_task-rest_bold.nii.gz',
        '/sub-01/anat/sub-01_T1w.nii.gz',
        '/sub-01/01_dwi.bvec',  # missed subject suffix
        '/sub-01/sub_dwi.json',  # missed subject id
        '/sub-01/sub-01_23_run-01_dwi.bval',  # wrong _23_
        '/sub-01/sub-01_run-01_dwi.vec',  # wrong extension
        '/sub-01/sub-01_run-01_dwi.jsn',  # wrong extension
        '/sub-01/sub-01_acq_dwi.bval',  # missed suffix value
        '/sub-01/sub-01_acq-23-singleband_dwi.bvec',  # redundant -23-
        '/sub-01/anat/sub-01_acq-singleband_dwi.json',  # redundant /anat/
        (
            '/sub-01/sub-01_recrod-record_acq-singleband_run-01_dwi.bval'
        ),  # redundant record-record_
        '/sub_01/sub-01_acq-singleband_run-01_dwi.bvec',  # wrong /sub_01/
        '/sub-01/sub-01_acq-singleband__run-01_dwi.json',  # wrong __
        '/sub-01/ses-test/sub-01_ses_test_dwi.bval',  # wrong ses_test
        '/sub-01/ses-test/sb-01_ses-test_dwi.bvec',  # wrong sb-01
        '/sub-01/ses-test/sub-01_ses-test_dw.json',  # wrong modality
        '/sub-01/ses-test/sub-01_ses-test_run-01_dwi.val',  # wrong extension
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband.bval',  # missed modality
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi',  # missed extension
        '/ses-test/sub-01/sub-01_ses-test_acq-singleband_dwi.json',  # wrong dirs order
        (
            '/sub-01/ses-test/sub-02_ses-test_acq-singleband_run-01_dwi.bval'
        ),  # wrong sub id in the filename
        '/sub-01/sub-01_ses-test_acq-singleband_run-01_dwi.bvec',  # ses dir missed
        '/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.json',  # sub id dir missed
    ],
)
def test_is_not_session_level(validator, fname):
    """Test that is_session_level returns false for non session level files."""
    assert not validator.is_session_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/sub-01_sessions.tsv',
        '/sub-01/sub-01_sessions.json',
    ],
)
def test_is_subject_level(validator, fname):
    """Test that is_subject_level returns true for subject level files."""
    assert validator.is_bids(fname)
    assert validator.is_subject_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/anat/sub-01_T1w.nii.gz',
        '/sub-02/sub-01_sessions.tsv',  # wrong sub id in the filename
        '/sub-01_sessions.tsv',  # missed subject id dir
        '/sub-01/sub-01_sesions.tsv',  # wrong modality
        '/sub-01/sub-01_sesions.ext',  # wrong extension
        '/sub-01/sub-01_sessions.jon',  # wrong extension
    ],
)
def test_is_not_subject_level(validator, fname):
    """Test that is_subject_level returns false for non subject level files."""
    assert not validator.is_subject_level(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/phenotype/measure.tsv',
        '/phenotype/measure.json',
    ],
)
def test_is_phenotypic(validator, fname):
    """Test that is_phenotypic returns true for phenotypic files."""
    assert validator.is_bids(fname)
    assert validator.is_phenotypic(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/anat/sub-01_T1w.nii.gz',
        '/measurement_tool_name.tsv',  # missed phenotype dir
        '/phentype/measurement_tool_name.josn',  # wrong phenotype dir
        '/phenotype/measurement_tool_name.jsn',  # wrong extension
    ],
)
def test_is_not_phenotypic(validator, fname):
    """Test that is_phenotypic returns false for non phenotypic files."""
    assert not validator.is_phenotypic(fname)


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-01/ses-1/func/sub-01_ses-1_task-rest_bold.nii.gz',
        '/sub-01/anat/sub-01_T1w.nii.gz',
    ],
)
def test_is_file(validator, fname):
    """Test that is_file returns true for file level files."""
    assert validator.is_bids(fname)
    assert validator.is_file(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        '/sub-01/anat/sub-1_T1w.json',  # subject inconsistency
        '/sub-01/anat/sub-01_dwi.nii.gz',  # wrong modality suffix
        '/sub-01/anat/sub-02_rec-CSD_T1w.json',  # subject inconsistency
        '/sub-01/anat/sub-01_rec-CS-D_T1w.nii.gz',  # rec label wrong
        '/sub-01/anat/sub-01_acq-23_T1W.json',  # modality suffix wrong
        '/sub-01/anat/sub-01_acq-23_rec-CSD_T1w.exe',  # wrong extension
        '/sub-01/anat/sub-01_acq-23_rec-CSD_T1w.niigz',  # extension typo
        '/sub-01/anat/sub-01_run-2-3_T1w.json',  # run label typo
        '/sub-01/anat/sub-01_rn-23_T1w.nii.gz',  # run typo
        # reconstruction label typo
        '/sub-01/ant/sub-01_rec-CS-D_run-23_T1w.json',
        '/sub-1/anat/sub-01_rec-CSD_run-23_t1w.nii.gz',  # T1w suffix typo
        '/sub-01/anat/sub-01_aq-23_run-23_T1w.json',  # acq typo
        '/sub-01/anat/sub-01_acq-23_run-23_dwi.nii.gz',  # wrong data type
        '/sub-01/anat/sub-01_acq-23_rc-CSD_run-23_T1w.json',  # rec typo
        # 2nd subject id typo
        '/sub-01/anat/sub-O1_acq-23_rec-CSD_run-23_T1w.nii.gz',
        # ses inconsistency
        '/sub-01/ses-test/anat/sub-01_ses-retest_T1w.json',
        # 2nd session typo
        '/sub-01/ses-test/anat/sub-01_sestest_T1w.nii.gz',
        # extension typo
        '/sub-01/ses-test/anat/sub-01_ses_test_rec-CSD_dwi.jsn',
        # wrong extension
        '/sub-01/ses_test/anat/sub-01_ses_test_rec-CSD_T1w.bval',
        # wrong extension
        '/sub-01/ses-test/anat/sub-01_ses-test_acq-23_T1w.exe',
    ],
)
def test_is_anat_false(validator, fname):
    """Test that is_bids returns False for invalid anat files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        # redundant suffix
        '/sub-01/dwi/sub-01_suffix-suff_acq-singleband_dwi.json',
        '/sub-01/dwi/sub-01_acq-singleband__run-01_dwi.nii.gz',  # wrong __
        '/sub-01/dwi/sub-01_acq_run-01_dwi.bval',  # missed -singleband in _acq
        '/sub-01/dwi/sub-01_acq-singleband_run_01_dwi.bvec',  # wrong run_01
        # wrong acq_singleband_
        '/sub-01/dwi/sub-01_acq_singleband_run-01_dwi.json',
        '/sub_01/ses-test/dwi/sub-01_ses-test_dwi.nii.gz',  # wrong sub_01 dir
        '/sub-01/ses_test/dwi/sub-01_ses-test_dwi.bval',  # wrong ses_test dir
        # wrong session in the filename
        '/sub-01/ses-retest/dwi/sub-01_ses-test_dwi.bvec',
        # wrong session in the filename
        '/sub-01/ses-test/dwi/sub-01_ses-retest_dwi.json',
        # wrong modality
        '/sub-01/ses-test/dwi/sub-01_ses-test_run-01_brain.nii.gz',
        '/sub-01/ses-test/dwi/sub-01_ses-test_run-01.bval',  # missed modality
        # wrong extension
        '/sub-01/ses-test/dwi/sub-01_ses-test_run-01_dwi.vec',
        '/sub-01/ses-test/dwi/sub-01_ses-test_run-01_dwi.jon',
        '/sub-01/ses-test/dwi/sub-01_ses-test_acq-singleband_dwi.ni.gz',
        '/sub-01/ses-test/dwi/sub-01_ses-test_acq-singleband_dwi.val',
        # wrong dirs order
        '/ses-test/dwi/sub-01/sub-01_ses-test_acq-singleband_dwi.bvec',
        '/sub-01/dwi/ses-test/sub-01_ses-test_acq-singleband_dwi.json',
        # wrong dirs order
        '/ses-test/sub-01/dwi/sub-01_ses-test_acq-singleband_run-01_dwi.nii.gz',
        # missed session id dir
        '/sub-01/dwi/sub-01_ses-test_acq-singleband_run-01_dwi.bvec',
        # missed sub id dir
        '/ses-test/dwi/sub-01_ses-test_acq-singleband_run-01_dwi.json',
    ],
)
def test_is_dwi_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        '/sub-01/ses-test/func/sub--01_ses-test_task-task_rec-rec_stim.tsv.gz',  # wrong --
        '/sub-01/ses-test/func/sub-01__ses-test_task-task_rec-rec_defacemask.nii.gz',  # wrong __
        '/sub-01/ses-test/func/sub-01_ses_test_task-task_rec-rec_defacemask.nii',  # wrong ses_test
        # missed session suffix and id in the filename
        '/sub-01/ses-test/func/sub-01_task-task_rec-rec_run-01_bold.nii.gz',
        # missed subject suffix and id in the filename
        '/sub-01/ses-test/func/ses-test_task-task_rec-rec_run-01_bold.nii',
        # wrong session id in the filename
        '/sub-01/ses-retest/func/sub-01_ses-test_task-task_rec-rec_run-01_sbref.nii.gz',
        # wrong subject id in the filename
        '/sub-01/ses-test/func/sub-02_ses-test_task-task_rec-rec_run-01_sbref.json',
        '/sub-01/ses-test/func/sub-01_ses-test_task-task_rec-rec_run-01.json',  # missed modality
        # missed extension
        '/sub-01/ses-test/func/sub-01_ses-test_task-task_rec-rec_run-01_events',
        # wrong dirs order
        '/sub-01/func/ses-test/sub-01_ses-test_task-task_rec-rec_run-01_physio.json',
        # wrong dirs order
        '/ses-test/func/sub-01/sub-01_ses-test_task-task_rec-rec_run-01_physio.tsv.gz',
        # wrong dirs order
        '/ses-test/sub-01/func/sub-01_ses-test_task-task_rec-rec_run-01_stim.json',
        # missed data type
        '/sub-01/ses-test/sub-01_ses-test_task-task_rec-rec_run-01_stim.tsv.gz',
        # missed session dir
        '/sub-01/func/sub-01_ses-test_task-task_rec-rec_run-01_defacemask.nii.gz',
        # missed subject dir
        '/ses-test/func/sub-01_ses-test_task-task_rec-rec_run-01_defacemask.nii',
    ],
)
def test_is_func_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        # various typos
        '/sub-01/func/sub-01_task-coding_sbref.ni.gz',  # ni
        '/sub-01/func/sub-01_task-coding_acq_23_bold.nii.gz',  # _23
        '/sub-01/func/sub-01_task-coding_acq-23_sbrf.nii.gz',  # sbrf
        '/sub-01/func/sub-02_task-coding_run-23_bold.nii.gz',  # sub-02
        '/sub-01/func/sub-01_task-coding-run-23_sbref.nii.gz',  # -run
        '/sub-01/func/sub-01_task_coding_acq-23_run-23_bold.nii.gz',  # _coding
        '/sub-01/func/sub-01-task-coding_acq-23_run-23_sbref.nii.gz',  # -task
        '/sub-01/ses-test/func/sub-01_ses-retest_task-coding_bold.nii.gz',  # ses-retest
        '/sub-01/ses-test/func/sub-02_ses-test_task-coding_sbref.nii.gz',  # sub-02
        '/sub-01/ses-test/func/sub-01_ses-test_task-coding_acq-23_blad.nii.gz',  # blad
        '/sub-01/ses-test/func/sub-01_ses-test-task-coding_acq-23_sbref.nii.gz',  # -task
        '/sub-01/ses-test/anat/sub-01_ses-test_task-coding_run-23_bold.nii.gz',  # anat
        '/sub-01/ses-test/anat/sub-01_ses-test_task-coding_run-23_sbref.nii.gz',  # anat
        '/sub-01/ses-test/dwi/sub-01_ses-test_task-coding_acq-23_run-23_bold.nii.gz',  # dwi
        '/sub-01/ses-test/dwi/sub-01_ses-test_task-coding_acq-23_run-23_sbref.nii.gz',  # dwi
    ],
)
def test_is_func_bold_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        '/sub-01/beeh/sub-01_task-task_events.tsv',  # wrong data type
        '/sub-01/beh/sub-01_suff-suff_task-task_events.json',  # wrong suffix
        '/sub-01/beh/sub-02_task-task_beh.json',  # wrong sub id in the filename
        '/sub-01/beh/sub-01_task_task_physio.json',  # wrong task_task
        '/sub-01/beh/sub-01_task-task_phycoo.tsv.gz',  # wrong modality
        '/sub-01/beh/sub-01_task-task_stim.jsn',  # wrong extension
        '/sub-01/beh/sub-01_task-task.tsv.gz',  # missed modality
        '/sub-01/ses-test/beh/sub-01_ses-test_task-task_events',  # missed extension
        '/sub-01/beh/ses-test/sub-01_ses-test_task-task_events.json',  # wrong dirs order
        '/ses-test/beh/sub-01/sub-01_ses-test_task-task_beh.json',  # wrong dirs order
        '/ses-test/sub-01/beh/sub-01_ses-test_task-task_physio.json',  # wrong dirs order
        '/sub-01/ses-test/sub-01_ses-test_task-task_physio.tsv.gz',  # missed data type dir
        '/sub-01/beh/sub-01_ses-test_task-task_stim.json',  # missed session id dir
        '/ses-test/beh/sub-01_ses-test_task-task_stim.tsv.gz',  # missed subject id dir
    ],
)
def test_is_behavioral_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        '/sub-01/ses-test/func/sub--01_ses-test_task-nback_physio.tsv.gz',  # wrong --
        '/sub-01/ses-test/func/sub-01__ses-test_task-nback_physio.json',  # wrong __
        '/sb-01/ses-test/func/sub-01_ses-test_task-nback_stim.tsv.gz',  # wrong subject dir
        '/sub-01/ss-test/func/sub-01_ses-test_task-nback_stim.json',  # wrong  session dir
        # wrong data type
        '/sub-01/ses-test/dwi/sub-01_ses-test_task-nback_recording-saturation_physio.tsv.gz',
        # wrong suffix tsk-
        '/sub-01/ses-test/func/sub-01_ses-test_tsk-nback_recording-saturation_physio.json',
        # wrong session id in the filename
        '/sub-01/ses-test/func/sub-01_ses-retest_task-nback_recording-saturation_stim.tsv.gz',
        # wrong subject id in the filename
        '/sub_01/ses-test/func/sub-02_ses-test_task-nback_recording-saturation_stim.json',
        '/sub-01/beh/ses-test/sub-01_ses-test_task-nback_physio.tsv.gz',  # wrong dirs order
        '/ses-test/beh/sub-01/sub-01_ses-test_task-nback_physio.json',  # wrong dirs order
        '/ses-test/sub-01/beh/sub-01_ses-test_task-nback_stim.tsv.gz',  # wrong dirs order
        '/sub-01/ses-test/beh/sub-01_ses-test_task-nback.json',  # missed modality
        # missed extension
        '/sub-01/ses-test/beh/sub-01_ses-test_task-nback_recording-saturation_physio.',
        # missed session id dir
        '/sub-01/beh/sub-01_ses-test_task-nback_recording-saturation_stim.tsv.gz',
        # missed sub id dir
        '/ses-test/beh/sub-01_ses-test_task-nback_recording-saturation_stim.json',
    ],
)
def test_is_cont_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname'),
    [
        '/sub-01/ses-test/fmap/sub--01_ses-test_acq-singleband_run-01_magnitude.json',  # wrong --
        '/sub-01/ses-test/fmap/sub-01_ses-test__acq-singleband_run-01_magnitude.nii',  # wrong __
        # wrong 01-ses
        '/sub-01/ses-test/fmap/sub-01-ses-test_acq-singleband_run-01_magnitude1.nii.gz',
        # wrong acq_singleband
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq_singleband_run-01_magnitude1.json',
        # wrong extension
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq-singleband_run-01_magnitude1.ni',
        # wrong modality
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq-singleband_run-01_magnitude3.nii.gz',
        # wrong ssuffix ran
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq-singeband_ran-01_magnitude2.json',
        # missed session id in the filename
        '/sub-01/ses-test/fmap/sub-01_acq-singleband_run-01_magnitude2.nii',
        # missed subject id in the filename
        '/sub-01/ses-test/fmap/ses-test_acq-singleband_run-01_fieldmap.nii.gz',
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq-singleband_run-01.json',  # missed modality
        '/sub-01/ses-test/fmap/sub-01_ses-test_acq-singleband_run-01_fieldmap',  # wrong extension
        # wrong dirs order
        '/sub-01/fmap/ses-test/sub-01_ses-test_acq-singleband_dir-dirlabel_epi.nii.gz',
        # wrong dirs order
        '/ses-test/fmap/sub-01/sub-01_ses-test_acq-singleband_dir-dirlabel_epi.json',
        # wrong dirs order
        '/ses-test/sub-01/fmap/sub-01_ses-test_acq-singleband_dir-dirlabel_epi.nii',
        # missed data type dir
        '/sub-01/ses-test/sub-01_ses-test_acq-singleband_dir-dirlabel_run-01_epi.nii.gz',
        # missed session dir
        '/sub-01/fmap/sub-01_ses-test_acq-singleband_dir-dirlabel_run-01_epi.json',
        # missed subject dir
        '/ses-test/fmap/sub-01_ses-test_acq-singleband_dir-dirlabel_run-01_epi.nii',
    ],
)
def test_is_field_map_false(validator, fname):
    """Test that is_bids returns False for invalid dwi files."""
    assert not validator.is_bids(fname)
