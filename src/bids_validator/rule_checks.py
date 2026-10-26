"""The schema's rules: which apply to a file, and what each one asks.

Everything the BIDS schema says about a file's content is written as a RULE WITH
SELECTORS. The selectors say when the rule applies; the rest of the rule, its
payload, says what must then be true. There are three kinds of payload:

====================  ==============================================  ================
payload               where in the schema                             handled by
====================  ==============================================  ================
``checks``            ``rules.checks``                                this module
``fields``            ``rules.sidecars``, ``rules.json``,             :mod:`.field_checks`
                      ``rules.dataset_metadata``
``columns`` (and      ``rules.tabular_data``                          :mod:`.table_checks`
``initial_columns``,
``index_columns``)
====================  ==============================================  ================

For one file, this module finds every rule whose selectors all hold, then hands each
payload of that rule to the module that knows it. That is the reference validator's
``applyRules.ts``: one walk over ``schema.rules``, one selector step, a table from
payload name to handler.

A ``checks`` rule looks like this::

    ReadmeFileSmall:
      issue:
        code: README_FILE_SMALL
        message: The recommended file '/README' is very small. ...
        level: warning
      selectors:
        - match(path, '^/README')     # when does the rule apply?
      checks:
        - size > 150                  # what must then be true?

It FAILS when it applies and at least one check is not true, and produces one
finding whose code, level and message come from its own ``issue`` block.

Expressions are evaluated by :func:`bids_validator.expression_language.interpret`.
How the result is read follows the schema's documentation: "if an expression
(selector or check) evaluates to null, the null will be interpreted equivalent to
false. That is, a null selector will not apply the current rule, and a null check
will fail."

Which rules run
---------------
A rule only runs when everything it reads is something this package provides.
:data:`NOT_ENABLED_YET` lists the parts of the context that are not built yet. A rule
that reads any of them is skipped, because evaluating it against a missing value
would report a problem that is not there: "a task scan needs an events file" would
fire on every task scan if the link to the events file is never made.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

import attrs
from bidsschematools import expressions as bst_expr

from .expression_language import interpret, parse, truthy
from .field_checks import field_issues
from .filename_checks import identified
from .issues import Issue, coded_issue, schema_issue
from .table_checks import column_issues, index_column_issues, initial_column_issues
from .walk import is_directory

if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from .context import Context

__all__ = [
    'NOT_ENABLED_YET',
    'PAYLOADS',
    'apply_rule',
    'evaluate',
    'names_read',
    'rule_issues',
    'runnable_rules',
]

logger = logging.getLogger(__name__)

# Context names a rule may NOT read yet. A rule reading any of them, or anything below
# them (``associations.events`` is below ``associations``), is skipped.
NOT_ENABLED_YET: tuple[str, ...] = (
    'associations',  # files that belong with this one (events, bval ...): issue #82
    'ome',  # OME-XML metadata of microscopy files: issue #52
    'tiff',  # TIFF header of microscopy files: issue #53
)

Rule = tuple[str, Mapping[str, Any]]  # (dotted schema path, rule)
Handler = Callable[[str, Mapping[str, Any], 'Context'], list[Issue]]

# Per-schema caches of the runnable rules. Schema objects live for the process, so
# id() is stable.
_RUNNABLE_MEMO: dict[int, list[Rule]] = {}
_PREPARED_MEMO: dict[int, list[_Prepared]] = {}

# A ``{...}`` placeholder in an issue message, such as ``{entities.atlas}``.
_PLACEHOLDER = re.compile(r'\{([^{}]+)\}')


def rule_issues(context: Context) -> list[Issue]:
    """Return every finding of every runnable schema rule, for one file.

    A plain folder is skipped: no rule is written for one. The rules see the context as
    filename identification left it (:func:`~bids_validator.filename_checks.identified`):
    a file that matched no filename rule has no suffix or extension for them to read.

    Parameters
    ----------
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        The findings, in schema order.

    """
    if is_directory(context):
        return []
    context = identified(context)
    issues: list[Issue] = []
    for prepared in _prepared_rules(context.schema):
        issues += _apply(prepared, context)
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
    return _apply(_prepare(path, rule), context)


@attrs.frozen
class _Prepared:
    """A rule read out of the schema once, for the loop that runs it on every file.

    The schema's ``Namespace`` is slow to read; a dataset asks every rule's selectors
    about every file, so they are copied out into plain tuples first.
    """

    path: str
    rule: Mapping[str, Any]
    selectors: tuple[str, ...]
    handlers: tuple[Handler, ...]  # in the rule's own order, as the reference


def _prepare(path: str, rule: Mapping[str, Any]) -> _Prepared:
    return _Prepared(
        path=path,
        rule=rule,
        selectors=tuple(str(selector) for selector in rule.get('selectors', [])),
        handlers=tuple(PAYLOADS[key] for key in rule.keys() if key in PAYLOADS),  # noqa: SIM118
    )


def _prepared_rules(schema: Namespace) -> list[_Prepared]:
    """Return :func:`runnable_rules` that have a payload, prepared; once per schema.

    ``rules.files`` and ``rules.errors`` entries carry selectors but no payload, so they
    can never report anything here; evaluating their selectors on every file would
    only cost time.
    """
    cached = _PREPARED_MEMO.get(id(schema))
    if cached is None:
        prepared = (_prepare(path, rule) for path, rule in runnable_rules(schema))
        cached = [rule for rule in prepared if rule.handlers]
        _PREPARED_MEMO[id(schema)] = cached
    return cached


def _apply(prepared: _Prepared, context: Context) -> list[Issue]:
    """Check a rule's selectors, then run each of its payloads."""
    # all() stops at the first false selector, so later selectors, which may assume
    # what earlier ones established, are not evaluated for files they do not suit.
    if not all(truthy(evaluate(s, context, prepared.path)) for s in prepared.selectors):
        return []
    issues: list[Issue] = []
    for handler in prepared.handlers:
        issues += handler(prepared.path, prepared.rule, context)
    return issues


def check_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``checks``: report the rule's issue if any check is not true."""
    if all(truthy(evaluate(check, context, path)) for check in rule['checks']):
        return []
    definition = rule.get('issue') or {}
    location = context.file.relative_path
    if not definition.get('code') or not definition.get('message'):
        # The reference validator's fallback for a rule without a complete issue.
        return [coded_issue(context.schema, 'CHECK_ERROR', location=location, rule=path)]
    message = _format_message(str(definition['message']), context, path)
    return [schema_issue(definition, location=location, message=message, rule=path)]


# Payload name -> handler, in the reference validator's order (``evalMap``).
PAYLOADS: dict[str, Handler] = {
    'checks': check_issues,
    'columns': column_issues,
    'initial_columns': initial_column_issues,
    'index_columns': index_column_issues,
    'fields': field_issues,
}


def runnable_rules(schema: Namespace) -> list[Rule]:
    """Return every rule with selectors that reads nothing in :data:`NOT_ENABLED_YET`.

    Computed once per schema. A rule whose expressions cannot be parsed is left out
    too, since it could only ever report a problem with the schema, not the dataset.

    Parameters
    ----------
    schema : Namespace
        The BIDS schema.

    Returns
    -------
    list of (str, Mapping)
        ``(dotted rule path, rule)`` pairs, in schema order.

    """
    cached = _RUNNABLE_MEMO.get(id(schema))
    if cached is not None:
        return cached
    runnable: list[Rule] = []
    for path, rule in _selector_rules(schema['rules'], 'rules'):
        try:
            names = names_read(rule)
        except Exception as error:  # noqa: BLE001 - pyparsing raises its own types
            logger.debug('Skipping %s: cannot parse it (%s)', path, error)
            continue
        if not any(_is_below(name, prefix) for name in names for prefix in NOT_ENABLED_YET):
            runnable.append((path, rule))
    _RUNNABLE_MEMO[id(schema)] = runnable
    return runnable


def names_read(rule: Mapping[str, Any]) -> set[str]:
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
        names.update(_reads(parse(expression)))
    return names


def evaluate(expression: str, context: Context, path: str) -> Any:
    """Evaluate one expression, reading any error as null.

    The reference validator does the same (``_evalCheck`` in its ``applyRules.ts``):
    an expression that raises counts as null, so a selector that raises does not
    apply the rule and a check that raises fails it. Logged at DEBUG level, so the
    cause can be found with ``logging.basicConfig(level=logging.DEBUG)``.
    """
    try:
        return interpret(expression, context)
    except Exception as error:  # noqa: BLE001 - any failure means "no value", by the spec
        logger.debug('%s: %r raised %r on %s', path, expression, error, context.path)
        return None


# --- rule walking ---------------------------------------------------------


def _selector_rules(node: Any, path: str) -> Iterator[Rule]:
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
        yield from _selector_rules(node[key], f'{path}.{key}')


# --- reading what a rule needs --------------------------------------------


def _reads(node: Any) -> Iterator[str]:
    """Yield the dotted names read anywhere in a parsed expression."""
    name = _dotted(node)
    if name is not None:
        yield name
        return
    match node:
        case bst_expr.Property(name=base):
            yield from _reads(base)
        case bst_expr.Element(name=base, index=index):
            yield from _reads(base)
            yield from _reads(index)
        case bst_expr.Function(args=args):
            for arg in args:
                yield from _reads(arg)
        case bst_expr.BinOp(lh=lh, rh=rh):
            yield from _reads(lh)
            yield from _reads(rh)
        case bst_expr.RightOp(rh=rh):
            yield from _reads(rh)
        case bst_expr.Array(elements=elements):
            for element in elements:
                yield from _reads(element)


def _dotted(node: Any) -> str | None:
    """Return ``a.b.c`` for a bare name or a chain of ``.field`` lookups, else None."""
    match node:
        case str() if node[:1] in ('"', "'") or node in ('true', 'false', 'null'):
            return None  # a string literal or a constant, not a read
        case str():
            return node
        case bst_expr.Property(name=base, field=field):
            prefix = _dotted(base)
            return f'{prefix}.{field}' if prefix is not None else None
    return None


def _is_below(name: str, prefix: str) -> bool:
    """Whether ``name`` is ``prefix`` itself or a field inside it."""
    return name == prefix or name.startswith(f'{prefix}.')


# --- building the finding -------------------------------------------------


def _format_message(message: str, context: Context, path: str) -> str:
    """Make the schema's message one line and fill in its ``{...}`` placeholders.

    Schema messages are multi-line YAML blocks, and a few name a value from the
    context, such as ``No /atlas-{entities.atlas}_description.json could be found.``
    The placeholder is an expression, evaluated for this file.
    """
    one_line = ' '.join(message.split())
    return _PLACEHOLDER.sub(
        lambda found: _display(evaluate(found.group(1), context, path)), one_line
    )


def _display(value: Any) -> str:
    """Show a value the way the reference validator prints it in a message."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return ','.join(_display(item) for item in value)
    return str(value)
