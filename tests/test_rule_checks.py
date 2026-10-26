"""Tests for the schema's rules: which apply, how they are evaluated, what they report."""

import pathlib
import typing as ty

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.checks import collect_issues
from bids_validator.context import Context, Dataset
from bids_validator.issues import Severity
from bids_validator.rule_checks import (
    NOT_ENABLED_YET,
    PAYLOADS,
    apply_rule,
    names_read,
    rule_issues,
    runnable_rules,
)
from bids_validator.types.files import FileTree

from .helpers import FULL_DESCRIPTION, LONG_README, gzipped, nifti, write


def rule_codes(root: pathlib.Path, schema: Namespace) -> set[tuple[str, str]]:
    """Return ``{(code, location)}`` for every rule finding in the dataset."""
    tree = FileTree.read_from_filesystem(str(root))
    issues = collect_issues(tree, schema, checks=(rule_issues,), dataset_checks=())
    return {(issue.code, issue.location or '') for issue in issues}


# --- which rules run --------------------------------------------------------


def test_only_unbuilt_parts_of_the_context_are_held_back() -> None:
    assert NOT_ENABLED_YET == ('associations', 'ome', 'tiff')


def test_no_runnable_rule_reads_a_held_back_name(schema: Namespace) -> None:
    for path, rule in runnable_rules(schema):
        for name in names_read(rule):
            blocked = [p for p in NOT_ENABLED_YET if name == p or name.startswith(f'{p}.')]
            assert not blocked, (path, name, blocked)


def test_every_kind_of_rule_runs(schema: Namespace) -> None:
    groups = {path.split('.')[1] for path, _rule in runnable_rules(schema)}
    assert {'checks', 'sidecars', 'json', 'dataset_metadata', 'tabular_data'} <= groups


def test_rules_reading_associations_wait(schema: Namespace) -> None:
    paths = {path for path, _rule in runnable_rules(schema)}
    assert 'rules.checks.events.EventsMissing' not in paths
    assert 'rules.checks.general.ReadmeFileSmall' in paths
    assert 'rules.checks.anat.T1wFileWithTooManyDimensions' in paths


@pytest.mark.parametrize(
    ('expression', 'expected'),
    [
        ('exists(substr(path, 0, length(path) - 3), "dataset") == 0', {'path'}),
        ('"micr" in dataset.modalities', {'dataset.modalities'}),
        ('nifti_header.dim[0] == 4', {'nifti_header.dim'}),
        ('sidecar.EchoTime[index(x, "a")] > 0', {'sidecar.EchoTime', 'x'}),
        ('match(extension, "\\.gz$")', {'extension'}),
        ('type(null) == "null"', set()),
    ],
)
def test_names_read(expression: str, expected: set[str]) -> None:
    assert names_read({'checks': [expression]}) == expected


def test_payloads_in_the_reference_order() -> None:
    assert list(PAYLOADS) == ['checks', 'columns', 'initial_columns', 'index_columns', 'fields']


# --- rules failing on bad data and quiet on good data -----------------------

# (code, files that make the rule fail, where it is reported, files that make it pass)
CASES = [
    pytest.param(
        'DUPLICATE_FILES',
        {'sub-01/anat/sub-01_T1w.nii.gz': '', 'sub-01/anat/sub-01_T1w.nii': ''},
        'sub-01/anat/sub-01_T1w.nii.gz',
        {'sub-01/anat/sub-01_T1w.nii.gz': ''},
        id='general.DuplicateFiles',
    ),
    pytest.param(
        'README_FILE_SMALL',
        {'README': 'too short'},
        'README',
        {'README': LONG_README},
        id='general.ReadmeFileSmall',
    ),
    pytest.param(
        'MULTIPLE_README_FILES',
        {'README': LONG_README, 'README.md': LONG_README},
        'README.md',
        {'README.md': LONG_README},
        id='general.DuplicateReadmes',
    ),
    pytest.param(
        'README_FILE_MISSING',
        {},
        'dataset_description.json',
        {'README.txt': LONG_README},
        id='hints.ReadmeFileMissing',
    ),
    pytest.param(
        'PHASE_SUFFIX_DEPRECATED',
        {'sub-01/func/sub-01_task-rest_phase.nii.gz': ''},
        'sub-01/func/sub-01_task-rest_phase.nii.gz',
        {'sub-01/func/sub-01_task-rest_bold.nii.gz': ''},
        id='func.PhaseSuffixDeprecated',
    ),
    pytest.param(
        'SAMPLES_TSV_MISSING',
        {'sub-01/micr/sub-01_sample-A_SEM.png': ''},
        'dataset_description.json',
        {
            'samples.tsv': 'sample_id\tparticipant_id\tsample_type\n',
            'sub-01/micr/sub-01_sample-A_SEM.png': '',
        },
        id='dataset.SamplesTSVMissing',
    ),
    pytest.param(
        'EXCESSIVE_ELECTRODE_SPECIFICITY',
        {'sub-01/eeg/sub-01_task-rest_electrodes.tsv': ''},
        'sub-01/eeg/sub-01_task-rest_electrodes.tsv',
        {'sub-01/eeg/sub-01_electrodes.tsv': ''},
        id='channels.ElectrodeSpecificity',
    ),
    pytest.param(
        'T1W_FILE_WITH_TOO_MANY_DIMENSIONS',
        {'sub-01/anat/sub-01_T1w.nii.gz': nifti((2, 2, 2, 2))},
        'sub-01/anat/sub-01_T1w.nii.gz',
        {'sub-01/anat/sub-01_T1w.nii.gz': nifti((2, 2, 2))},
        id='anat.T1wFileWithTooManyDimensions',
    ),
    pytest.param(
        'EVENT_ONSET_ORDER',
        {'sub-01/func/sub-01_task-rest_events.tsv': 'onset\tduration\n5\t1\n2\t1\n'},
        'sub-01/func/sub-01_task-rest_events.tsv',
        {'sub-01/func/sub-01_task-rest_events.tsv': 'onset\tduration\n2\t1\n5\t1\n'},
        id='events.SortedOnsets',
    ),
    pytest.param(
        'SUSPICIOUS_NEGATIVE_EVENT_ONSET',
        {'sub-01/func/sub-01_task-rest_events.tsv': 'onset\tduration\n-100\t1\n'},
        'sub-01/func/sub-01_task-rest_events.tsv',
        {'sub-01/func/sub-01_task-rest_events.tsv': 'onset\tduration\n-5\t1\n'},
        id='events.SuspiciousNegativeEventOnset',
    ),
    pytest.param(
        'GZIP_HEADER_MTIME',
        {'sub-01/func/sub-01_task-rest_events.tsv.gz': gzipped('x', mtime=1_700_000_000)},
        'sub-01/func/sub-01_task-rest_events.tsv.gz',
        {'sub-01/func/sub-01_task-rest_events.tsv.gz': gzipped('x', mtime=0)},
        id='privacy.GzipHeaderMtime',
    ),
    pytest.param(
        'TOO_FEW_AUTHORS',
        {'dataset_description.json': {**FULL_DESCRIPTION, 'Authors': ['Ada Lovelace']}},
        'dataset_description.json',
        {'dataset_description.json': FULL_DESCRIPTION},
        id='hints.TooFewAuthors',
    ),
    pytest.param(
        'UNKNOWN_BIDS_VERSION',
        {'dataset_description.json': {**FULL_DESCRIPTION, 'BIDSVersion': '9.9.9'}},
        'dataset_description.json',
        {'dataset_description.json': FULL_DESCRIPTION},
        id='dataset.UnknownVersion',
    ),
]


@pytest.mark.parametrize(('code', 'failing', 'location', 'passing'), CASES)
def test_rule_fails_on_bad_data_and_passes_on_good_data(
    tmp_path: pathlib.Path,
    schema: Namespace,
    code: str,
    failing: dict[str, ty.Any],
    location: str,
    passing: dict[str, ty.Any],
) -> None:
    assert (code, location) in rule_codes(write(tmp_path / 'bad', failing), schema)
    assert code not in {
        found for found, _ in rule_codes(write(tmp_path / 'good', passing), schema)
    }


def test_an_unreadable_header_is_not_a_failed_check(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """``nifti_header != null`` is false for an empty image: the rule does not apply.

    The empty image is reported once, by the integrity checks, not again here.
    """
    write(tmp_path, {'sub-01/anat/sub-01_T1w.nii.gz': b''})
    codes = {code for code, _ in rule_codes(tmp_path, schema)}
    assert 'T1W_FILE_WITH_TOO_MANY_DIMENSIONS' not in codes


def test_an_unrecognised_file_is_held_to_no_rule(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """A file matching no filename rule has no suffix or extension for the rules."""
    write(tmp_path, {'sub-01/anat/x-1_y.nii.gz': nifti((2, 2, 2))})
    assert not [
        loc for _, loc in rule_codes(tmp_path, schema) if loc == 'sub-01/anat/x-1_y.nii.gz'
    ]


# --- how one rule is evaluated ----------------------------------------------


@pytest.fixture
def readme_context(tmp_path: pathlib.Path, schema: Namespace) -> Context:
    tree = FileTree.read_from_filesystem(str(write(tmp_path, {'README': 'short'})))
    return Context(tree / 'README', Dataset(tree, schema), None)


ISSUE = {'code': 'TEST_CODE', 'message': 'Problem in {path}.', 'level': 'error'}


@pytest.mark.parametrize(
    ('selectors', 'checks', 'reported'),
    [
        pytest.param(['true'], ['true'], False, id='applies-and-holds'),
        pytest.param(['true'], ['false'], True, id='applies-and-fails'),
        pytest.param(['false'], ['false'], False, id='does-not-apply'),
        # The schema documentation: "a null selector will not apply the current rule,
        # and a null check will fail."
        pytest.param(['null'], ['false'], False, id='null-selector-does-not-apply'),
        pytest.param(['true'], ['null'], True, id='null-check-fails'),
        # An expression that raises counts as null, as in the reference validator.
        pytest.param(['len(path)'], ['false'], False, id='raising-selector-does-not-apply'),
        pytest.param(['true'], ['len(path)'], True, id='raising-check-fails'),
        # Every check must hold.
        pytest.param(['true'], ['true', 'false'], True, id='one-failing-check-is-enough'),
        pytest.param([], ['false'], True, id='no-selectors-applies-everywhere'),
    ],
)
def test_apply_rule(
    readme_context: Context, selectors: list[str], checks: list[str], reported: bool
) -> None:
    rule = {'selectors': selectors, 'checks': checks, 'issue': ISSUE}
    issues = apply_rule('rules.checks.test.Rule', rule, readme_context)
    assert bool(issues) is reported


def test_the_finding_comes_from_the_rule(readme_context: Context) -> None:
    rule = {'selectors': [], 'checks': ['false'], 'issue': ISSUE}
    [issue] = apply_rule('rules.checks.test.Rule', rule, readme_context)
    assert (issue.code, issue.severity, issue.location) == ('TEST_CODE', Severity.ERROR, 'README')
    assert issue.message == 'Problem in /README.'  # the placeholder is filled in
    assert issue.rule == 'rules.checks.test.Rule'


def test_a_rule_without_a_complete_issue_reports_check_error(readme_context: Context) -> None:
    rule = {'selectors': [], 'checks': ['false'], 'issue': {'level': 'error'}}
    [issue] = apply_rule('rules.checks.test.Rule', rule, readme_context)
    assert issue.code == 'CHECK_ERROR'


def test_each_payload_of_a_rule_runs(readme_context: Context) -> None:
    """A rule with checks AND fields reports from both, in the rule's own order."""
    rule = {
        'selectors': [],
        'checks': ['false'],
        'issue': ISSUE,
        'fields': {'Authors': 'required'},  # README is not JSON: json is empty
    }
    codes = [issue.code for issue in apply_rule('rules.json.test.Rule', rule, readme_context)]
    assert codes == ['TEST_CODE', 'JSON_KEY_REQUIRED']
