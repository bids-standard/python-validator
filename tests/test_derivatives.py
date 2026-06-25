"""Test BIDSValidator support for derivative filenames."""

import pytest

from bids_validator import BIDSValidator


@pytest.mark.parametrize(
    'fname',
    [
        '/sub-04/anat/sub-04_space-MNI152_T1w.nii.gz',  # space
        '/sub-04/anat/sub-04_space-MNI152_desc-preproc_T1w.nii.gz',  # space + desc
        '/sub-04/ses-02/func/sub-04_ses-02_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii',  # space + desc
        '/sub-04/ses-02/func/sub-04_ses-02_task-nback_run-02_space-T1w_label-brain_mask.nii',  # space + label
        '/sub-04/ses-01/func/sub-04_ses-01_task-nback_run-01_space-T1w_desc-preproc_bold.json',  # space + desc
        '/sub-01/anat/sub-01_res-1_T1w.nii.gz',  # res
        '/sub-01/anat/sub-01_space-MNI152_dseg.nii.gz',  # dseg suffix
    ],
)
def test_derivative_filenames_are_bids(fname: str) -> None:
    """Test that derivative filenames are recognized as valid BIDS."""
    assert BIDSValidator.is_bids(fname)


@pytest.mark.parametrize(
    ('fname', 'expected'),
    [
        (
            '/sub-04/anat/sub-04_space-MNI152_desc-preproc_T1w.nii.gz',
            {
                'subject': '04',
                'datatype': 'anat',
                'space': 'MNI152',
                'description': 'preproc',
                'suffix': 'T1w',
                'extension': '.nii.gz',
            },
        ),
        (
            '/sub-04/ses-02/func/sub-04_ses-02_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii',
            {
                'subject': '04',
                'session': '02',
                'datatype': 'func',
                'task': 'rest',
                'space': 'MNI152NLin2009cAsym',
                'description': 'preproc',
                'suffix': 'bold',
                'extension': '.nii',
            },
        ),
    ],
)
def test_parse_derivative_entities(fname: str, expected: dict[str, str]) -> None:
    """Test that parse() returns derivative-specific entities."""
    assert BIDSValidator.parse(fname) == expected
