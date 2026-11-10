"""The ``checks`` payload: expressions about a file that must all be true.

A ``rules.checks`` rule says WHEN it applies (its selectors, decided by the rule engine
in :mod:`.rules`) and WHAT must then be true (its ``checks``)::

    ReadmeFileSmall:                  # rules.checks.general.ReadmeFileSmall
      issue:
        code: README_FILE_SMALL
        message: The recommended file '/README' is very small. ...
        level: warning
      selectors:
        - match(path, '^/README')     # when does the rule apply?
      checks:
        - size > 150                  # what must then be true?

When the rule applies and a check is not true, the rule FAILS, and it reports its own
``issue``: the code, level and message come from the schema.

Every selector and check is an expression evaluated by
:func:`.expression_language.interpret`. :func:`evaluate_or_null` adds the one rule the
schema documents for applying them: "if an expression (selector or check) evaluates to
null, the null will be interpreted equivalent to false. That is, a null selector will
not apply the current rule, and a null check will fail."
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..expression_language import interpret, truthy
from ..issues import Issue, IssueDefinition, Severity

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from ..context import Context

# The names other modules are meant to import from this one.
__all__ = ['CHECK_ERROR', 'check_issues', 'evaluate_or_null']

# Where this module writes its debug messages. ``logging.basicConfig(level=logging.DEBUG)``
# in a script shows them; by default they are hidden.
logger = logging.getLogger(__name__)

# --- what this module reports --------------------------------------------
#
# A rules.checks rule defines its own issue (code, level, message) in the schema, read
# from the rule when it fails. CHECK_ERROR is defined only by the reference validator
# (bids-validator, src/issues/list.ts): it is reported for a rule whose issue block is
# incomplete.

# A rules.checks rule failed, but its issue block has no code or message.
CHECK_ERROR = IssueDefinition(
    'CHECK_ERROR',
    Severity.ERROR,
    'generic place holder for errors from failed `checks` evaluated from schema.',
)

# A ``{...}`` placeholder in an issue message, such as ``{entities.atlas}``.
_PLACEHOLDER = re.compile(r'\{([^{}]+)\}')


def check_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``checks``: report the rule's issue if any check is not true.

    Parameters
    ----------
    path : str
        Dotted schema path of the rule (``rules.checks.general.ReadmeFileSmall``).
    rule : Mapping
        The rule; its selectors already hold for this file.
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        Nothing when every check is true; otherwise the rule's own issue, once.

    """
    if all(truthy(evaluate_or_null(check, context, path)) for check in rule['checks']):
        return []
    block = rule.get('issue') or {}
    location = context.file.relative_path
    if not block.get('code') or not block.get('message'):
        return [CHECK_ERROR.make_issue(location, rule=path)]
    definition = IssueDefinition.from_schema(block)
    message = _fill_placeholders(definition.reason, context, path)
    return [definition.make_issue(location, message=message, rule=path)]


def evaluate_or_null(expression: str, context: Context, path: str) -> Any:
    """Evaluate one expression for a file, reading any error as null.

    The reference validator does the same (``_evalCheck`` in its ``applyRules.ts``):
    an expression that raises counts as null, so a selector that raises does not
    apply the rule and a check that raises fails it. The error is logged at DEBUG
    level, so its cause can be found.

    Parameters
    ----------
    expression : str
        A selector or a check, such as ``size > 150``.
    context : Context
        The file the expression is about.
    path : str
        The rule it belongs to, only for the debug message.

    Returns
    -------
    Any
        The value: a boolean, number, string, list, mapping, or ``None`` for null.

    """
    try:
        return interpret(expression, context)
    except Exception as error:  # noqa: BLE001 - any failure means "no value", by the spec
        logger.debug('%s: %r raised %r on %s', path, expression, error, context.path)
        return None


def _fill_placeholders(message: str, context: Context, path: str) -> str:
    """Fill in the ``{...}`` placeholders of a rule's message for this file.

    A few messages name a value from the context, such as
    ``No /atlas-{entities.atlas}_description.json could be found.`` The placeholder is
    an expression, evaluated for this file.
    """
    return _PLACEHOLDER.sub(
        lambda found: _display(evaluate_or_null(found.group(1), context, path)), message
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
