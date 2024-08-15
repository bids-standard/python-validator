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
    ('fname'),
    [
        ('/T1w.json'),
        ('/dataset_description.json'),
        ('/README'),
        ('/README.md'),
        ('/README.rst'),
        ('/CHANGES'),
        ('/participants.tsv'),
        ('/participants.json'),
    ],
)
def test_top_level_true(validator, fname):
    """Test that is_top_level returns true for top-level files."""
    assert validator.is_top_level(fname) is True


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
        ('/RADME'),  # typo
        ('/CANGES'),  # typo
    ],
)
def test_top_level(validator, fname):
    """Test that is_top_level returns false for non top-level files."""
    assert validator.is_top_level(fname) is False


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/code/'),
        ('/derivatives/'),
        ('/sourcedata/'),
        ('/stimuli/'),
        ('/sourcedata/unstructured_data.nii.gz'),
        ('/sourcedata/dicom_dir/xyz.dcm'),
        ('/code/my_analysis/analysis.py'),
        ('/derivatives/preproc/sub-01/anat/sub-01_desc-preproc_T1w.nii.gz'),
        ('/stimuli/pic.jpg'),
    ],
)
def test_associated_data_true(validator, fname):
    """Test that is_associated_data returns true for associated data."""
    assert validator.is_associated_data(fname) is True


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
        ('/CODE/'),
        ('/derivatves/'),
        ('/source/'),
        ('/stimli/'),
        ('/.git/'),
    ],
)
def test_associated_data_false(validator, fname):
    """Test that is_associated_data returns false for associated data."""
    assert validator.is_associated_data(fname) is False


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/ses-1/sub-01_ses-1_scans.tsv'),
        ('/sub-01/ses-1/sub-01_ses-1_scans.json'),
        ('/sub-01/sub-01_scans.tsv'),
        ('/sub-01/sub-01_scans.json'),
        ('/sub-01/ses-1/sub-01_ses-1_task-rest_bold.json'),
        ('/sub-01/sub-01_task-rest_bold.json'),
        ('/sub-01/ses-1/sub-01_ses-1_asl.json'),
        ('/sub-01/sub-01_asl.json'),
        ('/sub-01/ses-1/sub-01_ses-1_pet.json'),
        ('/sub-01/sub-01_pet.json'),
        ('/sub-01/ses-1/sub-01_ses-1_proc-test_channels.tsv'),
        ('/sub-01/ses-1/sub-01_ses-1_channels.json'),
        ('/sub-01/sub-01_proc-test_channels.tsv'),
        ('/sub-01/sub-01_channels.json'),
        ('/sub-01/ses-1/sub-01_ses-1_space-CapTrak_electrodes.tsv'),
        ('/sub-01/ses-1/sub-01_ses-1_coordsystem.json'),
        ('/sub-01/sub-01_space-CapTrak_electrodes.tsv'),
        ('/sub-01/sub-01_coordsystem.json'),
        ('/sub-01/ses-1/sub-01_ses-1_motion.json'),
        ('/sub-01/sub-01_motion.json'),
        ('/sub-01/ses-1/sub-01_ses-1_TEM.json'),
        ('/sub-01/sub-01_TEM.json'),
        ('/sub-01/ses-1/sub-01_ses-1_nirs.json'),
        ('/sub-01/sub-01_nirs.json'),
        ('/sub-01/sub-01_dwi.bval'),
        ('/sub-01/sub-01_dwi.bvec'),
        ('/sub-01/sub-01_dwi.json'),
        ('/sub-01/sub-01_run-01_dwi.bval'),
        ('/sub-01/sub-01_run-01_dwi.bvec'),
        ('/sub-01/sub-01_run-01_dwi.json'),
        ('/sub-01/sub-01_acq-singleband_dwi.bval'),
        ('/sub-01/sub-01_acq-singleband_dwi.bvec'),
        ('/sub-01/sub-01_acq-singleband_dwi.json'),
        ('/sub-01/sub-01_acq-singleband_run-01_dwi.bval'),
        ('/sub-01/sub-01_acq-singleband_run-01_dwi.bvec'),
        ('/sub-01/sub-01_acq-singleband_run-01_dwi.json'),
        ('/sub-01/ses-test/sub-01_ses-test_dwi.bval'),
        ('/sub-01/ses-test/sub-01_ses-test_dwi.bvec'),
        ('/sub-01/ses-test/sub-01_ses-test_dwi.json'),
        ('/sub-01/ses-test/sub-01_ses-test_run-01_dwi.bval'),
        ('/sub-01/ses-test/sub-01_ses-test_run-01_dwi.bvec'),
        ('/sub-01/ses-test/sub-01_ses-test_run-01_dwi.json'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.bval'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.bvec'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi.json'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.bval'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.bvec'),
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.json'),
    ],
)
def test_session_level_true(validator, fname):
    """Test that is_session_level returns true for session level files."""
    assert validator.is_session_level(fname) is True


@pytest.mark.parametrize(
    ('fname'),
    [
        # Mismatch sessions
        ('/sub-01/sub-01_ses-1_scans.tsv'),
        ('/sub-01/sub-01_ses-1_scans.json'),
        ('/sub-01/ses-1/sub-01_ses-2_scans.tsv'),
        # File-level
        ('/sub-01/ses-1/func/sub-01_ses-1_task-rest_bold.nii.gz'),
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
        ('/sub-01/01_dwi.bvec'),  # missed subject suffix
        ('/sub-01/sub_dwi.json'),  # missed subject id
        ('/sub-01/sub-01_23_run-01_dwi.bval'),  # wrong _23_
        ('/sub-01/sub-01_run-01_dwi.vec'),  # wrong extension
        ('/sub-01/sub-01_run-01_dwi.jsn'),  # wrong extension
        ('/sub-01/sub-01_acq_dwi.bval'),  # missed suffix value
        ('/sub-01/sub-01_acq-23-singleband_dwi.bvec'),  # redundant -23-
        ('/sub-01/anat/sub-01_acq-singleband_dwi.json'),  # redundant /anat/
        (
            '/sub-01/sub-01_recrod-record_acq-singleband_run-01_dwi.bval'
        ),  # redundant record-record_
        ('/sub_01/sub-01_acq-singleband_run-01_dwi.bvec'),  # wrong /sub_01/
        ('/sub-01/sub-01_acq-singleband__run-01_dwi.json'),  # wrong __
        ('/sub-01/ses-test/sub-01_ses_test_dwi.bval'),  # wrong ses_test
        ('/sub-01/ses-test/sb-01_ses-test_dwi.bvec'),  # wrong sb-01
        ('/sub-01/ses-test/sub-01_ses-test_dw.json'),  # wrong modality
        ('/sub-01/ses-test/sub-01_ses-test_run-01_dwi.val'),  # wrong extension
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband.bval'),  # missed modality
        ('/sub-01/ses-test/sub-01_ses-test_acq-singleband_dwi'),  # missed extension
        ('/ses-test/sub-01/sub-01_ses-test_acq-singleband_dwi.json'),  # wrong dirs order
        (
            '/sub-01/ses-test/sub-02_ses-test_acq-singleband_run-01_dwi.bval'
        ),  # wrong sub id in the filename
        ('/sub-01/sub-01_ses-test_acq-singleband_run-01_dwi.bvec'),  # ses dir missed
        ('/ses-test/sub-01_ses-test_acq-singleband_run-01_dwi.json'),  # sub id dir missed
    ],
)
def test_session_level_false(validator, fname):
    """Test that is_session_level returns false for non session level files."""
    assert validator.is_session_level(fname) is False


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/sub-01_sessions.tsv'),
        ('/sub-01/sub-01_sessions.json'),
    ],
)
def test_subject_level_true(validator, fname):
    """Test that is_subject_level returns true for subject level files."""
    assert validator.is_subject_level(fname) is True


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
        ('/sub-02/sub-01_sessions.tsv'),  # wrong sub id in the filename
        ('/sub-01_sessions.tsv'),  # missed subject id dir
        ('/sub-01/sub-01_sesions.tsv'),  # wrong modality
        ('/sub-01/sub-01_sesions.ext'),  # wrong extension
        ('/sub-01/sub-01_sessions.jon'),  # wrong extension
    ],
)
def test_subject_level_false(validator, fname):
    """Test that is_subject_level returns false for non subject level files."""
    assert validator.is_subject_level(fname) is False


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/phenotype/measure.tsv'),
        ('/phenotype/measure.json'),
    ],
)
def test_phenotypic_true(validator, fname):
    """Test that is_phenotypic returns true for phenotypic files."""
    assert validator.is_phenotypic(fname) is True


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
        ('/measurement_tool_name.tsv'),  # missed phenotype dir
        ('/phentype/measurement_tool_name.josn'),  # wrong phenotype dir
        ('/phenotype/measurement_tool_name.jsn'),  # wrong extension
    ],
)
def test_phenotypic_false(validator, fname):
    """Test that is_phenotypic returns false for non phenotypic files."""
    assert validator.is_phenotypic(fname) is False


@pytest.mark.parametrize(
    ('fname'),
    [
        ('/sub-01/ses-1/func/sub-01_ses-1_task-rest_bold.nii.gz'),
        ('/sub-01/anat/sub-01_T1w.nii.gz'),
    ],
)
def test_file_level(validator, fname):
    """Test that is_file returns true for file level files."""
    assert validator.is_file(fname) is True
