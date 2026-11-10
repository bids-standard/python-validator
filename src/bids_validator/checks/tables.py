"""The table payloads: the right columns, in the right order, with the right values.

``rules.tabular_data`` describes each kind of TSV file::

    EEGChannels:                      # rules.tabular_data.eeg.EEGChannels
      selectors: [datatype == "eeg", suffix == "channels", extension == ".tsv"]
      initial_columns: [name__channels, type__channels, units]
      columns:
        name__channels: required
        type__channels: required
        units: required
        description: optional
        ...
      additional_columns: allowed_if_defined

Three payloads, one function each, all following the reference validator's
``schema/tables.ts``:

* ``columns`` (:func:`column_issues`): every required column is present
  (``TSV_COLUMN_MISSING``); a column the rule does not list is allowed, must be
  defined in the sidecar, or is not allowed (``TSV_ADDITIONAL_COLUMNS_*``); and every
  value has the type the schema gives the column, refined by the sidecar's own
  definition of it (``TSV_VALUE_INCORRECT_TYPE``, ``TSV_COLUMN_TYPE_REDEFINED``).
* ``initial_columns`` (:func:`initial_column_issues`): the first columns are these, in
  this order (``TSV_COLUMN_ORDER_INCORRECT``).
* ``index_columns`` (:func:`index_column_issues`): no two rows share the same values
  in these columns (``TSV_INDEX_VALUE_NOT_UNIQUE``).

A cell holding ``n/a`` is always accepted. The rule engine (:mod:`.rules`) calls
these functions for every rule with one of these payloads whose selectors hold.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import attrs

from ..issues import Issue, IssueDefinition, Severity

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from ..context import Context

# The names other modules are meant to import from this one: the three payload handlers
# and the codes defined below.
__all__ = [
    'TSV_ADDITIONAL_COLUMNS_MUST_DEFINE',
    'TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED',
    'TSV_ADDITIONAL_COLUMNS_UNDEFINED',
    'TSV_COLUMN_MISSING',
    'TSV_COLUMN_ORDER_INCORRECT',
    'TSV_COLUMN_TYPE_REDEFINED',
    'TSV_INDEX_VALUE_NOT_UNIQUE',
    'TSV_PSEUDO_AGE_DEPRECATED',
    'TSV_VALUE_INCORRECT_TYPE',
    'AllowedValues',
    'column_issues',
    'index_column_issues',
    'initial_column_issues',
]

# --- what this module reports --------------------------------------------
#
# None of these codes is defined by the schema; they are the reference validator's
# (bids-validator, src/issues/list.ts).

# A required column is not in the table.
TSV_COLUMN_MISSING = IssueDefinition(
    'TSV_COLUMN_MISSING', Severity.ERROR, 'A required column is missing'
)
# A column the rule wants first is somewhere else.
TSV_COLUMN_ORDER_INCORRECT = IssueDefinition(
    'TSV_COLUMN_ORDER_INCORRECT', Severity.ERROR, 'Some TSV columns are in the incorrect order'
)
# A column the rule does not list, where the rule allows none.
TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED = IssueDefinition(
    'TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED',
    Severity.ERROR,
    'A TSV file has extra columns which are not allowed for its file type',
)
# An unlisted column the sidecar should define, and does not.
TSV_ADDITIONAL_COLUMNS_MUST_DEFINE = IssueDefinition(
    'TSV_ADDITIONAL_COLUMNS_MUST_DEFINE',
    Severity.ERROR,
    'Additional TSV columns must be defined in the associated JSON sidecar for this file type',
)
# An unlisted column, allowed, but not defined in the sidecar.
TSV_ADDITIONAL_COLUMNS_UNDEFINED = IssueDefinition(
    'TSV_ADDITIONAL_COLUMNS_UNDEFINED',
    Severity.WARNING,
    'A TSV file has extra columns which are not defined in its associated JSON sidecar',
)
# A sidecar's definition of a column contradicts the schema's.
TSV_COLUMN_TYPE_REDEFINED = IssueDefinition(
    'TSV_COLUMN_TYPE_REDEFINED',
    Severity.WARNING,
    'A column required in a TSV file has been redefined in a sidecar file. This redefinition '
    'is being ignored.',
)
# A cell whose value does not fit its column (text in a number column).
TSV_VALUE_INCORRECT_TYPE = IssueDefinition(
    'TSV_VALUE_INCORRECT_TYPE',
    Severity.ERROR,
    'A value in a column did not match the acceptable type for that column headers specified '
    'format.',
)
# ``89+`` in an ``age`` column.
TSV_PSEUDO_AGE_DEPRECATED = IssueDefinition(
    'TSV_PSEUDO_AGE_DEPRECATED',
    Severity.WARNING,
    'Use of the value "89+" in column "age" is deprecated. Use 89 for all ages 89 and over.',
)
# Two rows with the same values in the index columns.
TSV_INDEX_VALUE_NOT_UNIQUE = IssueDefinition(
    'TSV_INDEX_VALUE_NOT_UNIQUE',
    Severity.ERROR,
    'An index column(s) was specified for the tsv file and not all of the values for it are '
    'unique.',
)

# A column a rule does not list, by the rule's ``additional_columns``: what is reported
# when the sidecar does not define it (or, for ``not_allowed``, at all).
_EXTRA_COLUMN = {
    'not_allowed': TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED,
    'allowed_if_defined': TSV_ADDITIONAL_COLUMNS_MUST_DEFINE,
}

# The extensions of the files these payloads apply to; a rule may select other files too.
_TABLE_EXTENSIONS = ('.tsv', '.tsv.gz')

# The leading number of a string, as JavaScript's parseFloat reads it ("12abc" is 12).
_LEADING_NUMBER = re.compile(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')


# A read-only data class (see issues.py for what attrs does).
@attrs.frozen
class AllowedValues:
    """What a column's values must look like, from the schema and the sidecar together.

    Attributes
    ----------
    formats : tuple of str
        Format names (keys of ``schema.objects.formats``): any one will do.
    pattern : str or None
        A pattern of its own, used instead of the formats' patterns.
    units, levels, maximum, minimum
        Further constraints; ``levels`` is the allowed values.

    """

    formats: tuple[str, ...]
    pattern: str | None = None
    units: str | None = None
    levels: tuple[str, ...] | None = None
    maximum: float | None = None
    minimum: float | None = None


# Raised by _narrowed_by_sidecar and caught in _listed_column, where it becomes a
# TSV_COLUMN_TYPE_REDEFINED finding; an exception lets the reason travel with it.
class _SidecarContradictsSchema(Exception):
    """A sidecar definition that conflicts with the schema's, rather than narrowing it."""


def column_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``columns``: missing, extra and badly typed columns.

    Parameters
    ----------
    path : str
        Dotted schema path of the rule.
    rule : Mapping
        The rule; its selectors already hold for this file.
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        The findings. Only the first bad value of a column is reported.

    """
    if context.extension not in _TABLE_EXTENSIONS or not rule.get('columns'):
        return []
    objects = context.schema['objects']['columns']
    listed = {str(objects[key]['name']): key for key in rule['columns']}
    present = dict(context.columns or {})
    extra = [name for name in present if name not in listed]

    issues: list[Issue] = []
    for name in [*listed, *extra]:
        if name in listed:
            found, allowed = _listed_column(context, path, rule, listed[name], present)
        else:
            found, allowed = _extra_column(context, path, rule, name)
        issues += found
        if allowed is not None:
            issues += _value_issues(context, path, name, list(present[name]), allowed)
    return issues


def _listed_column(
    context: Context, path: str, rule: Mapping[str, Any], key: str, present: Mapping[str, Any]
) -> tuple[list[Issue], AllowedValues | None]:
    """Check a column the rule lists; return its findings and what its values may be.

    The allowed values are ``None`` when the column is absent, so there are no values to
    check. A required column is reported missing here unless it is one of the rule's
    initial columns, which :func:`initial_column_issues` reports instead.
    """
    column = context.schema['objects']['columns'][key]
    name = str(column['name'])
    location = context.file.relative_path
    if name not in present:
        required = _requirement(rule, key) == 'required'
        if required and key not in (rule.get('initial_columns') or []):
            missing = TSV_COLUMN_MISSING.make_issue(
                location, sub_code=name, rule=path, message=f'required column {name!r} is missing'
            )
            return [missing], None
        return [], None
    try:
        return [], _allowed_values(column, _sidecar_definition(context, name))
    except _SidecarContradictsSchema as error:
        redefined = TSV_COLUMN_TYPE_REDEFINED.make_issue(
            context.sidecar_origins.get(name, ''),
            sub_code=name,
            rule=path,
            message=str(error),
        )
        return [redefined], _allowed_by_schema(column)


def _extra_column(
    context: Context, path: str, rule: Mapping[str, Any], name: str
) -> tuple[list[Issue], AllowedValues | None]:
    """Check a column the rule does not list; return its findings and what its values may be.

    The rule's ``additional_columns`` decides: ``allowed`` (the default), only
    ``allowed_if_defined`` in the sidecar, or ``not_allowed``. A column the sidecar
    defines has its values checked against that definition.
    """
    allowed = str(rule.get('additional_columns', 'n/a'))
    definition = _sidecar_definition(context, name)
    if allowed == 'not_allowed' or definition is None:
        found = _EXTRA_COLUMN.get(allowed, TSV_ADDITIONAL_COLUMNS_UNDEFINED)
        location = context.file.relative_path
        return [found.make_issue(location, sub_code=name, rule=path, message=name)], None
    return [], _allowed_by_sidecar(definition)


def _sidecar_definition(context: Context, name: str) -> Mapping[str, Any] | None:
    """Return the sidecar's definition of a column (``{"Description": ...}``), if any."""
    definition = context.sidecar.get(name)
    return definition if isinstance(definition, Mapping) else None


def initial_column_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``initial_columns``: the first columns are these, in this order.

    A listed column that is absent and not required is left out of the count, so an
    optional column that is simply not used does not shift the others.
    """
    if (
        context.extension not in _TABLE_EXTENSIONS
        or not rule.get('columns')
        or not rule.get('initial_columns')
    ):
        return []
    objects = context.schema['objects']['columns']
    headers = list(context.columns or {})
    wanted = []
    for key in rule['initial_columns']:
        name = str(objects[key]['name'])
        index = headers.index(name) if name in headers else -1
        if _requirement(rule, key) == 'required' or index != -1:
            wanted.append((name, index))

    issues: list[Issue] = []
    for target, (name, index) in enumerate(wanted):
        if index == -1:
            found, message = TSV_COLUMN_MISSING, f'required initial column {target + 1} not found'
        elif index != target:
            found = TSV_COLUMN_ORDER_INCORRECT
            message = f'initial column {target + 1} found at position {index + 1}'
        else:
            continue
        issues.append(
            found.make_issue(
                context.file.relative_path, sub_code=name, rule=path, message=f'{name}: {message}'
            )
        )
    return issues


def index_column_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``index_columns``: no two rows share the same index values.

    Each repeated row is reported, with its line number (the header is line 1).
    """
    if (
        context.extension not in _TABLE_EXTENSIONS
        or not rule.get('columns')
        or not rule.get('index_columns')
    ):
        return []
    objects = context.schema['objects']['columns']
    columns: Mapping[str, Any] = context.columns or {}
    names = [str(objects[key]['name']) for key in rule['index_columns']]
    names = [name for name in names if name in columns]
    if not names:
        return []
    seen: set[str] = set()
    issues: list[Issue] = []
    for row in range(len(columns[names[0]])):
        value = ''.join(str(columns[name][row]) for name in names)
        if value in seen:
            issues.append(
                TSV_INDEX_VALUE_NOT_UNIQUE.make_issue(
                    context.file.relative_path,
                    rule=path,
                    message=f'row {row + 2}, value {value!r}',
                )
            )
        else:
            seen.add(value)
    return issues


# --- value types ----------------------------------------------------------


def _value_issues(
    context: Context, path: str, name: str, values: list[str], allowed: AllowedValues
) -> list[Issue]:
    """Report the first value of a column that is not allowed.

    ``89+`` in an ``age`` column is the one exception: deprecated rather than wrong,
    and warned about once.
    """
    if _allows_anything(allowed):
        return []
    pattern = allowed.pattern
    if pattern is None:
        formats = context.schema['objects']['formats']
        if any(fmt not in formats.keys() for fmt in allowed.formats):  # noqa: SIM118
            return []  # an unknown format: nothing to check against
        pattern = '|'.join(str(formats[fmt]['pattern']) for fmt in allowed.formats)
    # Anchored the way the reference validator anchors it: "^" + pattern + "$",
    # without grouping the alternatives.
    compiled = re.compile(f'^{pattern}$')

    issues: list[Issue] = []
    age_warned = False
    for row, value in enumerate(values):
        if _is_allowed(value, compiled, allowed):
            continue
        if name == 'age' and value == '89+':
            if not age_warned:
                age_warned = True
                issues.append(
                    TSV_PSEUDO_AGE_DEPRECATED.make_issue(
                        context.file.relative_path, message=f'line {row + 2}'
                    )
                )
            continue
        hint = ", did you mean 'n/a'?" if re.fullmatch(r'\s*(NA|na|nan|NaN|n/a)\s*', value) else ''
        issues.append(
            TSV_VALUE_INCORRECT_TYPE.make_issue(
                context.file.relative_path,
                sub_code=name,
                rule=path,
                message=f'line {row + 2}: {value!r}{hint}',
            )
        )
        break
    return issues


def _is_allowed(value: str, pattern: re.Pattern[str], allowed: AllowedValues) -> bool:
    """Whether one cell is allowed. ``n/a`` always is."""
    if value == 'n/a':
        return True
    if not pattern.search(value):
        return False
    if allowed.levels is not None and value not in allowed.levels:
        return False
    if allowed.maximum is not None or allowed.minimum is not None:
        number = _parse_float(value)
        if allowed.maximum is not None and not number <= allowed.maximum:
            return False
        if allowed.minimum is not None and not number >= allowed.minimum:
            return False
    return True


def _allowed_values(
    column: Mapping[str, Any], definition: Mapping[str, Any] | None
) -> AllowedValues:
    """Return what a listed column may hold: the schema's rules, narrowed by the sidecar.

    A column whose schema object has a ``definition`` (a conventional column, such as
    ``trial_type``) is fully defined by the sidecar when the sidecar defines it.
    """
    if 'definition' in column.keys():  # noqa: SIM118
        return _allowed_by_sidecar(definition or column['definition'])
    base = _allowed_by_schema(column)
    return (
        _narrowed_by_sidecar(base, _allowed_by_sidecar(definition))
        if definition is not None
        else base
    )


def _allowed_by_schema(column: Mapping[str, Any]) -> AllowedValues:
    """Return what the schema allows in a column."""
    levels = column.get('enum')
    return AllowedValues(
        formats=tuple(_formats(column)),
        pattern=column.get('pattern'),
        units=column.get('unit'),
        levels=tuple(str(level) for level in levels) if levels is not None else None,
        maximum=column.get('maximum'),
        minimum=column.get('minimum'),
    )


def _allowed_by_sidecar(definition: Mapping[str, Any]) -> AllowedValues:
    """Return what a sidecar's column definition allows (``Format``, ``Levels`` ...)."""
    fmt = definition.get('Format') or ('number' if definition.get('Units') else 'string')
    levels = definition.get('Levels')
    return AllowedValues(
        formats=(str(fmt),),
        units=definition.get('Units'),
        levels=tuple(str(level) for level in levels) if isinstance(levels, Mapping) else None,
        maximum=definition.get('Maximum'),
        minimum=definition.get('Minimum'),
    )


def _narrowed_by_sidecar(base: AllowedValues, override: AllowedValues) -> AllowedValues:
    """Combine what the schema allows with what the sidecar says, which may only narrow it.

    Raises :class:`_SidecarContradictsSchema` when the sidecar contradicts the schema: another kind
    of value (text where the schema wants numbers), levels outside the schema's,
    different units, or wider bounds.
    """
    kinds = {_kind(fmt) for fmt in base.formats}
    if _kind(override.formats[0]) not in kinds:
        raise _SidecarContradictsSchema(
            f'format {override.formats[0]!r} must be {" or ".join(base.formats)}'
        )
    levels = override.levels if override.levels is not None else base.levels
    if (
        base.levels is not None
        and override.levels is not None
        and not set(override.levels) <= set(base.levels)
    ):
        raise _SidecarContradictsSchema(
            f'levels {{{", ".join(override.levels)}}} are not a subset of '
            f'{{{", ".join(base.levels)}}}'
        )
    units = override.units if override.units is not None else base.units
    if base.units is not None and units != base.units:
        raise _SidecarContradictsSchema(f'unit {units!r} must be {base.units!r}')
    minimum = override.minimum if override.minimum is not None else base.minimum
    if base.minimum is not None and minimum is not None and minimum < base.minimum:
        raise _SidecarContradictsSchema(f'minimum {minimum} is less than {base.minimum}')
    maximum = override.maximum if override.maximum is not None else base.maximum
    if base.maximum is not None and maximum is not None and maximum > base.maximum:
        raise _SidecarContradictsSchema(f'maximum {maximum} is greater than {base.maximum}')
    return AllowedValues(
        formats=override.formats,
        pattern=base.pattern,
        units=units,
        levels=levels,
        maximum=maximum,
        minimum=minimum,
    )


def _formats(column: Mapping[str, Any]) -> list[str]:
    """Return the format names a schema column allows, following ``anyOf``."""
    alternatives = column.get('anyOf')
    if isinstance(alternatives, list):
        return [fmt for alternative in alternatives for fmt in _formats(alternative)]
    return [str(column.get('format') or column.get('type') or 'string')]


def _kind(fmt: str) -> str:
    """Collapse a format to the kind of value it holds: number, boolean or string."""
    return {'integer': 'number', 'number': 'number', 'boolean': 'boolean'}.get(fmt, 'string')


def _allows_anything(allowed: AllowedValues) -> bool:
    """Whether every value would pass, so there is nothing to check."""
    return (
        allowed.levels is None
        and allowed.maximum is None
        and allowed.minimum is None
        and (
            (allowed.pattern is None and allowed.formats[0] == 'string') or allowed.pattern == '.*'
        )
    )


def _requirement(rule: Mapping[str, Any], key: str) -> str:
    """Return a column's requirement level in a rule: ``required``, ``recommended`` ..."""
    requirement = rule['columns'].get(key)
    if isinstance(requirement, Mapping):
        return str(requirement.get('level'))
    if requirement is not None:
        return str(requirement)
    return str(rule.get('additional_columns', 'n/a'))


def _parse_float(text: str) -> float:
    """JavaScript's ``parseFloat``: the leading number of a string, else NaN."""
    found = _LEADING_NUMBER.match(text)
    return float(found.group(0)) if found else float('nan')
