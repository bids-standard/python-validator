"""Tests for the schema-driven filename checks (names and places only)."""

import json
import pathlib

import fsspec
import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator import BIDSValidator
from bids_validator.checks import collect_issues
from bids_validator.context import Context, Dataset
from bids_validator.filename_checks import SIDECAR_EXTENSIONS, filename_issues, identified
from bids_validator.issues import REFERENCE_CODES, Severity
from bids_validator.types.files import FileTree

from .helpers import build
from .helpers import codes as all_codes

VALID = 'sub-01/anat/sub-01_T1w.nii.gz'


def codes(root: pathlib.Path, schema: Namespace) -> dict[str, list[str]]:
    """Map each filename code found to the locations it was found at."""
    return all_codes(root, schema, filename_issues)


def test_valid_dataset_has_no_findings(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, VALID, 'sub-01/func/sub-01_task-rest_bold.nii.gz', 'README')
    assert codes(tmp_path, schema) == {}


@pytest.mark.parametrize(
    ('relpath', 'expected'),
    [
        ('sub-01/notes.txt', 'NOT_INCLUDED'),
        ('sub-01/anat/sub-01_T1w.txt', 'EXTENSION_MISMATCH'),
        ('sub-01/func/sub-01_bold.nii.gz', 'MISSING_REQUIRED_ENTITY'),
        ('sub-01/anat/sub-01_acq-_T1w.nii.gz', 'ENTITY_WITH_NO_LABEL'),
        ('sub-01/anat/sub-01_foo_T1w.nii.gz', 'ENTITY_WITH_NO_LABEL'),
        ('sub-01/anat/sub-01_acq-a!b_T1w.nii.gz', 'INVALID_ENTITY_LABEL'),
        ('sub-01/anat/sub-01_dir-AP_T1w.nii.gz', 'ENTITY_NOT_IN_RULE'),
        ('sub-01/anat/acq-x_sub-01_T1w.nii.gz', 'FILENAME_MISMATCH'),
        ('sub-01/func/sub-01_T1w.nii.gz', 'DATATYPE_MISMATCH'),
        ('sub-01/sub-01_T1w.nii.gz', 'MISSING_DATATYPE'),
        ('sub-02/anat/sub-01_T1w.nii.gz', 'INVALID_LOCATION'),
    ],
)
def test_each_code_fires(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str, expected: str
) -> None:
    build(tmp_path, relpath)
    found = codes(tmp_path, schema)
    assert expected in found, f'{relpath} should raise {expected}, got {sorted(found)}'
    assert relpath in found[expected]


def test_findings_are_errors_and_carry_location(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/notes.txt')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    issues = collect_issues(tree, schema, checks=(filename_issues,), dataset_checks=())
    assert len(issues) == 1
    assert issues.has_errors
    issue = issues.issues[0]
    assert issue.severity is Severity.ERROR
    assert issue.location == 'sub-01/notes.txt'
    assert issue.message


def test_rule_path_recorded_for_rule_scoped_findings(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    build(tmp_path, 'sub-01/func/sub-01_bold.nii.gz')
    tree = FileTree.read_from_filesystem(str(tmp_path))
    issues = collect_issues(tree, schema, checks=(filename_issues,), dataset_checks=())
    issue = next(iter(issues))
    assert issue.code == 'MISSING_REQUIRED_ENTITY'
    assert issue.rule is not None
    assert issue.rule.startswith('rules.files.')


def test_every_code_is_in_the_catalog() -> None:
    """Every code this module can emit has a severity and a reason."""
    for code in (
        'NOT_INCLUDED',
        'ENTITY_WITH_NO_LABEL',
        'INVALID_ENTITY_LABEL',
        'MISSING_REQUIRED_ENTITY',
        'ENTITY_NOT_IN_RULE',
        'MISSING_DATATYPE',
        'DATATYPE_MISMATCH',
        'EXTENSION_MISMATCH',
        'INVALID_LOCATION',
        'FILENAME_MISMATCH',
        'ALL_FILENAME_RULES_HAVE_ISSUES',
        'CASE_COLLISION',
    ):
        severity, reason = REFERENCE_CODES[code]
        assert severity is Severity.ERROR
        assert reason


# --- folders --------------------------------------------------------------


@pytest.mark.parametrize(
    ('folder', 'reported'),
    [
        ('sub-01/foo/', True),  # not a datatype, not an entity, not a named folder
        ('stuff/', True),
        ('sub-01/', False),  # an entity folder
        ('sub-01/ses-1/', False),
        ('sub-01/anat/', False),  # a datatype folder
        ('phenotype/', False),  # a named folder
    ],
)
def test_folder_names_are_checked(
    tmp_path: pathlib.Path, schema: Namespace, folder: str, reported: bool
) -> None:
    """A folder must match ``rules.directories``, as in the reference validator."""
    build(tmp_path, folder)
    assert (folder in codes(tmp_path, schema).get('NOT_INCLUDED', [])) is reported


def test_a_file_in_a_bogus_folder_reports_both(tmp_path: pathlib.Path, schema: Namespace) -> None:
    """The folder is not BIDS, and the image beside it is not in a datatype folder."""
    build(tmp_path, 'sub-01/foo/sub-01_T1w.nii.gz')
    found = codes(tmp_path, schema)
    assert 'sub-01/foo/' in found['NOT_INCLUDED']
    assert 'sub-01/foo/sub-01_T1w.nii.gz' in found['MISSING_DATATYPE']
    # the legacy check agrees this is not a valid BIDS path
    assert not BIDSValidator().is_bids('/sub-01/foo/sub-01_T1w.nii.gz')


@pytest.mark.parametrize(
    'relpath',
    [
        'task-rest_bold.json',  # inherited sidecar at the dataset root
        'sub-01/sub-01_T1w.json',  # sidecar one level above the data
        'sub-01/sub-01_scans.tsv',  # subject-level tabular metadata
        'sub-01/sub-01_task-rest_events.tsv',  # events inherited upward
        'dwi.bvec',  # gradient tables are inheritable too
        'dwi.bval',
    ],
)
def test_inheritable_metadata_may_sit_above_the_datatype_directory(
    tmp_path: pathlib.Path, schema: Namespace, relpath: str
) -> None:
    """The inheritance principle allows these; they must not be flagged."""
    build(tmp_path, VALID, relpath)
    assert codes(tmp_path, schema) == {}


def test_sidecar_extensions_are_the_reference_list() -> None:
    assert frozenset({'.json', '.tsv', '.bvec', '.bval'}) == SIDECAR_EXTENSIONS


def test_a_sidecar_in_the_wrong_datatype_folder_is_not_flagged(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """``func/sub-01_T1w.json`` could describe data elsewhere; the reference skips it."""
    build(tmp_path, VALID, 'sub-01/func/sub-01_T1w.json')
    assert codes(tmp_path, schema) == {}


# --- letter case ----------------------------------------------------------


@pytest.fixture
def memfs() -> fsspec.AbstractFileSystem:
    """An in-memory file system: case-sensitive, unlike a default macOS disk."""
    mem = fsspec.filesystem('memory')
    mem.store.clear()
    yield mem
    mem.store.clear()


def test_names_differing_only_by_case_collide(
    memfs: fsspec.AbstractFileSystem, schema: Namespace
) -> None:
    memfs.pipe(
        {
            '/ds/dataset_description.json': json.dumps(
                {'Name': 't', 'BIDSVersion': '1.11.1'}
            ).encode(),
            '/ds/sub-01/anat/sub-01_T1w.nii.gz': b'x',
            '/ds/sub-01/anat/sub-01_t1w.nii.gz': b'x',
        }
    )
    tree = FileTree.read_from_filesystem('memory:///ds')
    issues = collect_issues(tree, schema, checks=(filename_issues,), dataset_checks=())
    collisions = [i.location or '' for i in issues if i.code == 'CASE_COLLISION']
    assert sorted(collisions) == ['sub-01/anat/sub-01_T1w.nii.gz', 'sub-01/anat/sub-01_t1w.nii.gz']


# --- what the schema rules see --------------------------------------------


def test_an_unrecognised_file_has_no_name_parts_for_the_rules(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """``identified`` clears what no matched rule uses, as the reference's cleanContext."""
    tree = FileTree.read_from_filesystem(str(build(tmp_path, VALID, 'sub-01/anat/x-1_notes.txt')))
    dataset = Dataset(tree, schema)

    unknown = identified(Context(tree / 'sub-01' / 'anat' / 'x-1_notes.txt', dataset, None))
    assert (unknown.entities, unknown.suffix, unknown.extension) == ({}, '', '')

    readme_tree = FileTree.read_from_filesystem(str(build(tmp_path / 'r', 'README')))
    readme = identified(Context(readme_tree / 'README', Dataset(readme_tree, schema), None))
    assert readme.entities == {}

    image = Context(tree / 'sub-01' / 'anat' / 'sub-01_T1w.nii.gz', dataset, None)
    assert identified(image) is image  # nothing to clear: the context itself


# --- derivatives and recordings -------------------------------------------


def test_derivatives_are_not_checked_against_the_parent_dataset_rules(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A derivative is a separate dataset; its files must not be judged by raw rules."""
    build(tmp_path, VALID)
    deriv = tmp_path / 'derivatives' / 'mypipeline'
    build(deriv, 'sub-01/anat/sub-01_desc-preproc_T1w.nii.gz', 'logs/run.txt')
    assert codes(tmp_path, schema) == {}


def test_a_derivative_can_be_validated_as_its_own_dataset(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Pointing the checks at the derivative root makes the derivative rules apply."""
    deriv = build(tmp_path, VALID) / 'derivatives' / 'mypipeline'
    build(deriv, 'sub-01/anat/sub-01_desc-preproc_T1w.nii.gz')
    (deriv / 'dataset_description.json').write_text(
        json.dumps(
            {
                'Name': 'deriv',
                'BIDSVersion': '1.11.1',
                'DatasetType': 'derivative',
                'GeneratedBy': [{'Name': 'mypipeline'}],
            }
        )
    )
    # desc- is a derivative-only entity, so this name is legal here and nowhere else.
    assert codes(deriv, schema) == {}


def _make_recording(root: pathlib.Path, name: str) -> None:
    """Create a CTF-style directory recording with a vendor-named internal file."""
    recording = root / 'sub-01' / 'meg' / name
    recording.mkdir(parents=True)
    (recording / 'x.meg4').write_bytes(b'')
    (recording / 'BadChannels').write_bytes(b'')


def test_directory_recording_with_a_valid_name_is_clean(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """The folder name is valid, and its vendor-named internals are never checked."""
    build(tmp_path)
    _make_recording(tmp_path, 'sub-01_task-rest_meg.ds')
    assert codes(tmp_path, schema) == {}


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('oopsbadname.ds', 'NOT_INCLUDED'),  # not a BIDS name: an ordinary, bad folder
        ('sub-01_meg.ds', 'MISSING_REQUIRED_ENTITY'),  # missing the required task
    ],
)
def test_directory_recording_name_is_validated(
    tmp_path: pathlib.Path, schema: Namespace, name: str, expected: str
) -> None:
    """A directory recording is one unit, but its own name still follows the rules."""
    build(tmp_path)
    _make_recording(tmp_path, name)
    found = codes(tmp_path, schema)
    assert expected in found, f'{name} should raise {expected}, got {sorted(found)}'
    assert f'sub-01/meg/{name}/' in found[expected]
