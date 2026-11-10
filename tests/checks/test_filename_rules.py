"""Tests for the filename rules: read from the schema, and which describe a file."""

import fnmatch
import json
import pathlib

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.checks.filename_rules import (
    FilenameRule,
    all_filename_rules,
    matching_filename_rules,
)
from bids_validator.checks.walk import is_plain_folder, iter_contexts
from bids_validator.context import Context, Dataset
from bids_validator.types.files import FileTree

from ..helpers import build


def rules_by_path(schema: Namespace) -> dict[str, FilenameRule]:
    return {rule.path: rule for rule in all_filename_rules(schema)}


def contexts(root: pathlib.Path, schema: Namespace) -> dict[str, Context]:
    """Every file's context, by dataset-relative path."""
    dataset = Dataset(FileTree.read_from_filesystem(str(root)), schema)
    return {
        context.file.relative_path: context
        for context in iter_contexts(dataset)
        if not is_plain_folder(context)
    }


def test_rules_are_read_into_plain_values(schema: Namespace) -> None:
    anat = rules_by_path(schema)['rules.files.raw.anat.nonparametric']
    assert 'T1w' in (anat.suffixes or ())
    assert anat.datatypes == ('anat',)
    assert anat.entities is not None
    assert 'sub' in anat.entities  # short names, as in filenames
    assert 'acq' in anat.entities
    assert anat.required_entities == ('sub',)
    assert anat.fixed_path is None
    assert anat.stem is None


def test_a_list_the_rule_does_not_have_is_none(schema: Namespace) -> None:
    """None means "the rule says nothing", which is not an empty list."""
    description = rules_by_path(schema)['rules.files.common.core.dataset_description']
    assert description.fixed_path == 'dataset_description.json'
    assert (description.suffixes, description.entities, description.datatypes) == (
        None,
        None,
        None,
    )


def test_a_file_is_identified_by_suffix_path_or_stem(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    build(tmp_path, 'sub-01/anat/sub-01_T1w.nii.gz', 'participants.tsv', 'README')
    found = {
        path: [rule.path for rule in matching_filename_rules(c)]
        for path, c in contexts(tmp_path, schema).items()
    }
    assert found['sub-01/anat/sub-01_T1w.nii.gz'] == ['rules.files.raw.anat.nonparametric']
    assert found['dataset_description.json'] == ['rules.files.common.core.dataset_description']
    assert found['participants.tsv'] == ['rules.files.common.tables.participants']
    assert found['README'] == ['rules.files.common.core.README']


def test_a_file_that_is_not_bids_has_no_rule(tmp_path: pathlib.Path, schema: Namespace) -> None:
    build(tmp_path, 'sub-01/notes.txt')
    assert matching_filename_rules(contexts(tmp_path, schema)['sub-01/notes.txt']) == ()


def test_the_rule_for_the_files_folder_is_preferred(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """Many datatypes have an events file; the one in func/ is a func events file."""
    build(tmp_path, 'sub-01/func/sub-01_task-x_events.tsv')
    rules = matching_filename_rules(
        contexts(tmp_path, schema)['sub-01/func/sub-01_task-x_events.tsv']
    )
    assert rules
    assert all('func' in (rule.datatypes or ()) for rule in rules)


@pytest.mark.parametrize(('derivative', 'expected'), [(False, False), (True, True)])
def test_derivative_rules_apply_only_to_derivatives(
    tmp_path: pathlib.Path, schema: Namespace, derivative: bool, expected: bool
) -> None:
    build(tmp_path, 'sub-01/anat/sub-01_desc-brain_mask.nii.gz')
    if derivative:
        description = {'Name': 'd', 'BIDSVersion': '1.11.1', 'DatasetType': 'derivative'}
        (tmp_path / 'dataset_description.json').write_text(json.dumps(description))
    rules = matching_filename_rules(
        contexts(tmp_path, schema)['sub-01/anat/sub-01_desc-brain_mask.nii.gz']
    )
    assert any(rule.for_derivatives for rule in rules) is expected


def test_the_index_finds_what_comparing_every_rule_finds(
    tmp_path: pathlib.Path, schema: Namespace
) -> None:
    """The index is only a shortcut: it must find exactly the rules a full scan finds."""
    build(
        tmp_path,
        'sub-01/anat/sub-01_T1w.nii.gz',
        'sub-01/func/sub-01_task-x_bold.nii.gz',
        'sub-01/func/sub-01_task-x_events.tsv',
        'sub-01/sub-01_scans.tsv',
        'participants.json',
        'phenotype/survey.tsv',
        'task-x_bold.json',
        'sub-01/notes.txt',
        'CHANGES',
    )
    for context in contexts(tmp_path, schema).values():
        scanned = [rule for rule in all_filename_rules(schema) if _matches(rule, context)]
        found = matching_filename_rules(context)  # the best of what matched, so never more
        assert set(found) <= set(scanned)
        assert bool(found) == bool(scanned)


def _matches(rule: FilenameRule, context: Context) -> bool:
    """A full, unindexed test of one rule, written out plainly."""
    if rule.for_derivatives:
        return False  # these datasets are raw
    if rule.fixed_path is not None and f'/{rule.fixed_path}' == context.path:
        return True
    if rule.stem is not None and fnmatch.fnmatchcase(context.file.name.split('.')[0], rule.stem):
        return rule.datatypes is None or context.datatype in rule.datatypes
    return context.suffix in (rule.suffixes or ())
