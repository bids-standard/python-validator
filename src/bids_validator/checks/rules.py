"""The rule engine: which of the schema's rules apply to a file, and who checks them.

Everything the BIDS schema says about a file's content is written as a RULE WITH
SELECTORS. The selectors say WHEN the rule applies; the rest of the rule, its payload,
says WHAT must then be true. This module reports nothing itself. For one file it finds
every rule whose selectors all hold, and hands each payload of that rule to the module
that knows how to check it:

====================  ==============================================  ====================
payload               where in the schema                             checked by
====================  ==============================================  ====================
``checks``            ``rules.checks``                                :mod:`.expressions`
``fields``            ``rules.sidecars``, ``rules.json``,             :mod:`.fields`
                      ``rules.dataset_metadata``
``columns`` (and      ``rules.tabular_data``                          :mod:`.tables`
``initial_columns``,
``index_columns``)
====================  ==============================================  ====================

That is the reference validator's ``applyRules.ts``: one walk over ``schema.rules``, one
selector step, a table from payload name to handler.

Which rules run
---------------
A rule only runs when everything it reads is something this package provides.
:data:`NOT_ENABLED_YET` lists the parts of the context that are not built yet. A rule
that reads any of them is skipped, because evaluating it against a missing value
would report a problem that is not there: "a task scan needs an events file" would
fire on every task scan if the link to the events file is never made.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

import attrs
from bidsschematools import expressions as bst_expr

from ..expression_language import parse, truthy
from ..issues import Issue
from .expressions import check_issues, evaluate_or_null
from .fields import field_issues
from .filename_rules import hide_unused_name_parts, matching_filename_rules
from .schema_cache import once_per_schema
from .tables import column_issues, index_column_issues, initial_column_issues

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from ..context import Context

# The names other modules are meant to import from this one.
__all__ = [
    'NOT_ENABLED_YET',
    'PAYLOAD_HANDLERS',
    'PreparedRule',
    'apply_rule',
    'names_read_by',
    'rule_issues',
    'runnable_rules',
]

# Where this module writes its debug messages (a rule that cannot be parsed).
logger = logging.getLogger(__name__)

# Context names a rule may NOT read yet. A rule reading any of them, or anything below
# them (``associations.events`` is below ``associations``), is skipped.
NOT_ENABLED_YET: tuple[str, ...] = (
    'associations',  # files that belong with this one (events, bval ...): issue #82
    'ome',  # OME-XML metadata of microscopy files: issue #52
    'tiff',  # TIFF header of microscopy files: issue #53
)

# Two type aliases: names for types written out in full below, so a signature can say
# ``-> list[Rule]`` instead of ``-> list[tuple[str, Mapping[str, Any]]]``.
#
# A rule as found in the schema: its dotted path and the rule itself.
Rule = tuple[str, Mapping[str, Any]]
# A payload handler: takes (rule path, rule, file context), returns the findings.
PayloadHandler = Callable[[str, Mapping[str, Any], 'Context'], list[Issue]]

# Payload name -> the function that checks it, in the reference validator's order
# (``evalMap`` in applyRules.ts). A rule with several payloads runs them in its own order.
PAYLOAD_HANDLERS: dict[str, PayloadHandler] = {
    'checks': check_issues,
    'columns': column_issues,
    'initial_columns': initial_column_issues,
    'index_columns': index_column_issues,
    'fields': field_issues,
}


def rule_issues(context: Context) -> list[Issue]:
    """Return every finding of every runnable schema rule, for one file.

    The rules see the file as its name identifies it
    (:func:`~bids_validator.checks.filename_rules.hide_unused_name_parts`): a file that matched
    no filename rule has no suffix or extension for them to read.

    Parameters
    ----------
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        The findings, in schema order.

    """
    context = hide_unused_name_parts(context, matching_filename_rules(context))
    issues: list[Issue] = []
    for rule in _prepared_rules(context.schema):
        issues += _issues_from_rule(rule, context)
    return issues


def apply_rule(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Apply one rule to one file: check its selectors, then run each payload.

    Parameters
    ----------
    path : str
        Dotted schema path of the rule, for example
        ``rules.checks.general.ReadmeFileSmall``. Recorded on every finding.
    rule : Mapping
        The rule itself: ``selectors`` and one or more payloads.
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        Nothing when a selector is not true; otherwise whatever the payloads report.

    """
    return _issues_from_rule(_prepare(path, rule), context)


# --- applying a rule ------------------------------------------------------


# A read-only data class (see issues.py for what attrs does).
@attrs.frozen
class PreparedRule:
    """A rule read out of the schema once, for the loop that runs it on every file.

    The schema's ``Namespace`` is slow to read; a dataset asks every rule's selectors
    about every file, so they are copied out into plain tuples first.

    Attributes
    ----------
    path : str
        Dotted schema path of the rule.
    rule : Mapping
        The rule itself, handed to the payload handlers.
    selectors : tuple of str
        The expressions that must all hold for the rule to apply.
    handlers : tuple of PayloadHandler
        One per payload of the rule, in the rule's own order, as in the reference.

    """

    path: str
    rule: Mapping[str, Any]
    selectors: tuple[str, ...]
    handlers: tuple[PayloadHandler, ...]


def _prepare(path: str, rule: Mapping[str, Any]) -> PreparedRule:
    """Copy a rule's selectors and payload handlers out of the schema."""
    return PreparedRule(
        path=path,
        rule=rule,
        selectors=tuple(str(selector) for selector in rule.get('selectors', [])),
        handlers=tuple(
            PAYLOAD_HANDLERS[key]
            for key in rule.keys()  # noqa: SIM118 - see _rules_with_selectors
            if key in PAYLOAD_HANDLERS
        ),
    )


@once_per_schema
def _prepared_rules(schema: Namespace) -> list[PreparedRule]:
    """Return the :func:`runnable_rules` that have a payload, prepared.

    ``rules.files`` and ``rules.errors`` entries carry selectors but no payload, so they
    can never report anything here; evaluating their selectors on every file would
    only cost time.
    """
    prepared = (_prepare(path, rule) for path, rule in runnable_rules(schema))
    return [rule for rule in prepared if rule.handlers]


def _issues_from_rule(rule: PreparedRule, context: Context) -> list[Issue]:
    """Check a rule's selectors, then run each of its payloads."""
    # all() stops at the first false selector, so later selectors, which may assume
    # what earlier ones established, are not evaluated for files they do not suit.
    if not all(truthy(evaluate_or_null(s, context, rule.path)) for s in rule.selectors):
        return []
    issues: list[Issue] = []
    for handler in rule.handlers:
        issues += handler(rule.path, rule.rule, context)
    return issues


# --- which rules run ------------------------------------------------------


@once_per_schema
def runnable_rules(schema: Namespace) -> list[Rule]:
    """Return every rule with selectors that reads nothing in :data:`NOT_ENABLED_YET`.

    A rule whose expressions cannot be parsed is left out too, since it could only
    ever report a problem with the schema, not the dataset.

    Parameters
    ----------
    schema : Namespace
        The BIDS schema.

    Returns
    -------
    list of (str, Mapping)
        ``(dotted rule path, rule)`` pairs, in schema order.

    """
    runnable: list[Rule] = []
    for path, rule in _rules_with_selectors(schema['rules'], 'rules'):
        try:
            names = names_read_by(rule)
        except Exception as error:  # noqa: BLE001 - pyparsing raises its own types
            logger.debug('Skipping %s: cannot parse it (%s)', path, error)
            continue
        if not any(_is_inside(name, held) for name in names for held in NOT_ENABLED_YET):
            runnable.append((path, rule))
    return runnable


def names_read_by(rule: Mapping[str, Any]) -> set[str]:
    """Return every context name a rule reads, as dotted paths.

    ``exists(substr(path, 0, length(path) - 3), "dataset")`` reads ``{'path'}``;
    ``"micr" in dataset.modalities`` reads ``{'dataset.modalities'}``;
    ``nifti_header.dim[0] == 4`` reads ``{'nifti_header.dim'}``. Function names
    and string literals are not reads.

    Parameters
    ----------
    rule : Mapping
        A rule with ``selectors`` and/or ``checks``.

    Returns
    -------
    set of str
        The dotted names.

    """
    names: set[str] = set()
    for expression in [*rule.get('selectors', []), *rule.get('checks', [])]:
        names.update(_names_in(parse(expression)))
    return names


def _rules_with_selectors(node: Any, path: str) -> Iterator[Rule]:
    """Yield ``(dotted path, rule)`` for every node with ``selectors`` below ``node``.

    In practice that is ``rules.checks``, ``rules.sidecars``, ``rules.json``,
    ``rules.dataset_metadata`` and ``rules.tabular_data`` (``rules.errors`` has
    selectors but no payload). Walking to any node with selectors keeps a new group
    in a future schema working. ``.keys()`` is used on purpose: a bidsschematools
    Namespace reads a dotted key as a path and can insert into the schema.
    """
    if not isinstance(node, Mapping):
        return
    if 'selectors' in node.keys():  # noqa: SIM118
        yield path, node
        return
    for key in node:
        yield from _rules_with_selectors(node[key], f'{path}.{key}')


def _names_in(node: Any) -> Iterator[str]:
    """Yield the dotted names read anywhere in a parsed expression."""
    name = _dotted_name(node)
    if name is not None:
        yield name
        return
    # ``match``/``case`` picks the branch whose pattern fits the node's type, and binds
    # its fields: ``case bst_expr.BinOp(lh=lh, rh=rh)`` runs for a binary operation and
    # names its two sides ``lh`` and ``rh``.
    match node:
        case bst_expr.Property(name=base):
            yield from _names_in(base)
        case bst_expr.Element(name=base, index=index):
            yield from _names_in(base)
            yield from _names_in(index)
        case bst_expr.Function(args=args):
            for arg in args:
                yield from _names_in(arg)
        case bst_expr.BinOp(lh=lh, rh=rh):
            yield from _names_in(lh)
            yield from _names_in(rh)
        case bst_expr.RightOp(rh=rh):
            yield from _names_in(rh)
        case bst_expr.Array(elements=elements):
            for element in elements:
                yield from _names_in(element)


def _dotted_name(node: Any) -> str | None:
    """Return ``a.b.c`` for a bare name or a chain of ``.field`` lookups, else None."""
    match node:
        case str() if node[:1] in ('"', "'") or node in ('true', 'false', 'null'):
            return None  # a string literal or a constant, not a read
        case str():
            return node
        case bst_expr.Property(name=base, field=field):
            prefix = _dotted_name(base)
            return f'{prefix}.{field}' if prefix is not None else None
    return None


def _is_inside(name: str, prefix: str) -> bool:
    """Whether ``name`` is ``prefix`` itself or a field inside it."""
    return name == prefix or name.startswith(f'{prefix}.')
