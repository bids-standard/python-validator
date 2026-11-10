"""Run every check on a dataset: one walk, every check, one list of findings.

This is the only place that says WHICH checks run and IN WHAT ORDER. Each check is a
plain function in its own module, and there are three kinds:

=========================================  ===========================================
check                                      question it answers
=========================================  ===========================================
**the dataset** (``Dataset -> list``)
:func:`.dataset_integrity_issues`          is there a ``dataset_description.json``?
**each folder** (``Context -> list``)
:func:`.folder_issues`                     is the folder's name legal?
**each file** (``Context -> list``)
:func:`.integrity_issues`                  can the file be read at all?
:func:`.inheritance_issues`                does a deeper sidecar change a value?
:func:`.filename_issues`                   is the name, and the place, legal?
:func:`.rule_issues`                       do the schema's rules hold (checks, fields,
                                           columns)?
=========================================  ===========================================

The dataset is checked first. Then :mod:`.walk` visits every file and
folder, and each gets the checks of its kind, in the reference validator's order
(``validators/bids.ts``): problems reading the file first, then its name, then the
schema's rules. A directory recording (``sub-01_task-x_meg.ds/``) is a folder on disk
but a file to BIDS, so it gets the file checks.

A file's context is built once and shared by every check, so whatever it has loaded
(its sidecar, its header) is loaded once.

The modules of this package
---------------------------
Grouped by how a check works, one module per family of checks:

=========================  =========================================================
module                     what it holds
=========================  =========================================================
:mod:`.walk`               which files and folders a validation visits
:mod:`.integrity`          files that cannot be read the way their type needs
:mod:`.inheritance`        a deeper sidecar changing a value set above it
:mod:`.filenames`          names and places of files and folders
:mod:`.filename_rules`     which of the schema's filename rules a name matches
:mod:`.rules`              the rule engine: which schema rules apply to a file, and
                           which module checks each part of a rule
:mod:`.expressions`        the ``checks`` part of a rule: expressions that must hold
:mod:`.fields`             the ``fields`` part: keys of sidecars and JSON files
:mod:`.tables`             the ``columns`` parts: the columns of TSV tables
:mod:`.values`             one value against its schema definition (for fields and
                           tables)
:mod:`.schema_cache`       reading something out of the schema once per schema
=========================  =========================================================

What they build on lives outside the package: :mod:`bids_validator.context` (what is
known about one file), :mod:`bids_validator.expression_language` (evaluating the
schema's expressions) and :mod:`bids_validator.issues` (what a finding is).
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

# Each import below is one check, from the module that owns it.
from ..context import Dataset
from ..issues import DatasetIssues, Issue
from .filenames import filename_issues, folder_issues
from .inheritance import inheritance_issues
from .integrity import dataset_integrity_issues, integrity_issues
from .rules import rule_issues
from .walk import is_plain_folder, iter_contexts

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from ..context import Context
    from ..types.files import FileTree

# The names other modules are meant to import from this one.
__all__ = ['DATASET_CHECKS', 'FILE_CHECKS', 'FOLDER_CHECKS', 'collect_issues']

# Two type aliases: names for "the shape of a check function", used in the hints below.
# ``Callable[[Dataset], list[Issue]]`` means "a function that takes a Dataset and returns
# a list of Issue". A dataset check gets the whole dataset; a context check gets one file
# or one folder (its Context).
DatasetCheck = Callable[[Dataset], list[Issue]]
ContextCheck = Callable[['Context'], list[Issue]]

# The checks themselves, in the order they run. Each is a tuple of functions (not of
# function calls: no brackets), so ``collect_issues`` can call each one on each item.
# ``tuple[DatasetCheck, ...]`` means "a tuple of any length whose items are dataset
# checks". To add a check, write the function and add it to the right tuple.

# Run once, before the walk.
DATASET_CHECKS: tuple[DatasetCheck, ...] = (dataset_integrity_issues,)

# Run on every plain folder the walk visits.
FOLDER_CHECKS: tuple[ContextCheck, ...] = (folder_issues,)

# Run on every file (and directory recording) the walk visits, in this order.
FILE_CHECKS: tuple[ContextCheck, ...] = (
    integrity_issues,  # can it be read?            integrity.py
    inheritance_issues,  # inherited values changed?  inheritance.py
    filename_issues,  # legal name and place?      filenames.py
    rule_issues,  # the schema's rules          rules.py
)


def collect_issues(
    tree: FileTree,
    schema: Namespace,
    *,
    dataset_checks: Iterable[DatasetCheck] = DATASET_CHECKS,
    folder_checks: Iterable[ContextCheck] = FOLDER_CHECKS,
    file_checks: Iterable[ContextCheck] = FILE_CHECKS,
) -> DatasetIssues:
    """Validate a dataset: every check, on everything it applies to, in order.

    Parameters
    ----------
    tree : FileTree
        The dataset root, from ``FileTree.read_from_filesystem(root)``.
    schema : Namespace
        The BIDS schema to validate against, from ``bidsschematools.schema.load_schema()``.
    dataset_checks, folder_checks, file_checks : iterables of callables, optional
        The checks to run; all of them by default. Pass fewer to run only some, for
        example ``dataset_checks=(), folder_checks=(), file_checks=(filename_issues,)``.
        (The ``*`` in the signature makes these keyword-only: they must be given by name.)

    Returns
    -------
    DatasetIssues
        The dataset's findings first, then each file's and folder's, in walk order.

    """
    dataset = Dataset(tree, schema)
    # Iterables can only be read once; tuples can be read for every file.
    folder_checks, file_checks = tuple(folder_checks), tuple(file_checks)
    issues = DatasetIssues()
    for dataset_check in dataset_checks:
        issues.extend(dataset_check(dataset))
    for context in iter_contexts(dataset):
        for check in folder_checks if is_plain_folder(context) else file_checks:
            issues.extend(check(context))
    return issues
