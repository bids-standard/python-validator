# ruff: noqa: D100

import attrs

from bids_validator.types.files import FileTree


def test_FileTree(examples):
    """Test the FileTree class."""
    ds000117 = FileTree.read_from_filesystem(examples / 'ds000117')
    assert 'sub-01/ses-mri/anat/sub-01_ses-mri_acq-mprage_T1w.nii.gz' in ds000117
    assert ds000117.children['sub-01'].parent is ds000117

    # Verify that evolving FileTrees creates consistent structures
    evolved = attrs.evolve(ds000117)
    assert evolved.children['sub-01'].parent is not ds000117
    assert evolved.children['sub-01'].parent is evolved
    assert evolved.children['sub-01'].children['ses-mri'].parent is not ds000117.children['sub-01']
    assert evolved.children['sub-01'].children['ses-mri'].parent is evolved.children['sub-01']
