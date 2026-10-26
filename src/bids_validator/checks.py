"""Run every check on a dataset: one walk, every check, one list of findings.

This is the only place that says WHICH checks run and IN WHAT ORDER. Each check is a
plain function in its own module:

=====================================  ==========================================
per-file check (``Context -> list``)   question it answers
=====================================  ==========================================
:func:`.integrity_issues`              can the file be read at all?
:func:`.inheritance_issues`            does a deeper sidecar change a value?
:func:`.filename_issues`               is the name, and the place, legal?
:func:`.rule_issues`                   do the schema's rules hold (checks, fields,
                                       columns)?
=====================================  ==========================================

and one per-dataset check, :func:`.dataset_integrity_issues` (is there a
``dataset_description.json``?), which runs first.

The order is the reference validator's (``validators/bids.ts``): problems reading
the file first (its context loaders report them), then the filename, then the
schema rules. :mod:`bids_validator.walk` decides which files and folders are
visited. A file's context is built once and shared by every check, so whatever it
has loaded (its sidecar, its header) is loaded once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from .context import Dataset
from .field_checks import inheritance_issues
from .filename_checks import filename_issues
from .integrity_checks import dataset_integrity_issues, integrity_issues
from .issues import DatasetIssues, Issue
from .rule_checks import rule_issues
from .walk import iter_contexts

if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from .context import Context
    from .types.files import FileTree

__all__ = ['PER_DATASET_CHECKS', 'PER_FILE_CHECKS', 'collect_issues']

FileCheck = Callable[['Context'], list[Issue]]
DatasetCheck = Callable[[Dataset], list[Issue]]

PER_FILE_CHECKS: tuple[FileCheck, ...] = (
    integrity_issues,
    inheritance_issues,
    filename_issues,
    rule_issues,
)

PER_DATASET_CHECKS: tuple[DatasetCheck, ...] = (dataset_integrity_issues,)


def collect_issues(
    tree: FileTree,
    schema: Namespace,
    *,
    checks: Iterable[FileCheck] = PER_FILE_CHECKS,
    dataset_checks: Iterable[DatasetCheck] = PER_DATASET_CHECKS,
) -> DatasetIssues:
    """Validate a dataset: every check, every file, in order.

    Parameters
    ----------
    tree : FileTree
        The dataset root, from ``FileTree.read_from_filesystem(root)``.
    schema : Namespace
        The BIDS schema to validate against.
    checks : iterable of callables, optional
        The per-file checks to run; all of them by default. Pass one to run only that
        family, for example ``checks=(filename_issues,)``.
    dataset_checks : iterable of callables, optional
        The per-dataset checks to run; all of them by default.

    Returns
    -------
    DatasetIssues
        The dataset-level findings, then each file's, in walk order.

    """
    dataset = Dataset(tree, schema)
    checks = tuple(checks)
    issues = DatasetIssues()
    for dataset_check in dataset_checks:
        issues.extend(dataset_check(dataset))
    for context in iter_contexts(dataset):
        for check in checks:
            issues.extend(check(context))
    return issues
