"""Check tables: the right columns, in the right order, with the right values.

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

A cell holding ``n/a`` is always accepted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import attrs

from .context import sidecar_origins
from .issues import Issue, coded_issue

if TYPE_CHECKING:
    from .context import Context

__all__ = ['column_issues', 'index_column_issues', 'initial_column_issues']

_TABLE_EXTENSIONS = ('.tsv', '.tsv.gz')

# The leading number of a string, as JavaScript's parseFloat reads it ("12abc" is 12).
_LEADING_NUMBER = re.compile(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')


@attrs.frozen
class Signature:
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


class _Redefined(Exception):
    """A sidecar definition that conflicts with the schema's, rather than refining it."""


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
    schema = context.schema
    objects = schema['objects']['columns']
    by_name = {str(objects[key]['name']): key for key in rule['columns']}
    present = dict(context.columns or {})
    names = list(by_name) + [name for name in present if name not in by_name]

    issues: list[Issue] = []
    for name in names:
        key = by_name.get(name)
        definition = context.sidecar.get(name)
        definition = definition if isinstance(definition, Mapping) else None
        location = context.file.relative_path

        if key is None:  # a column the rule does not list
            allowed = str(rule.get('additional_columns', 'n/a'))
            if allowed == 'not_allowed' or definition is None:
                code = {
                    'not_allowed': 'TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED',
                    'allowed_if_defined': 'TSV_ADDITIONAL_COLUMNS_MUST_DEFINE',
                }.get(allowed, 'TSV_ADDITIONAL_COLUMNS_UNDEFINED')
                issues.append(
                    coded_issue(
                        schema, code, location=location, sub_code=name, rule=path, message=name
                    )
                )
                continue
            signature = _from_definition(definition)
        else:
            if name not in present:
                required = _requirement(rule, key) == 'required'
                if required and key not in (rule.get('initial_columns') or []):
                    issues.append(
                        coded_issue(
                            schema,
                            'TSV_COLUMN_MISSING',
                            location=location,
                            sub_code=name,
                            rule=path,
                            message=f'required column {name!r} is missing',
                        )
                    )
                continue
            try:
                signature = _signature(objects[key], definition)
            except _Redefined as error:
                issues.append(
                    coded_issue(
                        schema,
                        'TSV_COLUMN_TYPE_REDEFINED',
                        location=sidecar_origins(context.file).get(name, ''),
                        sub_code=name,
                        rule=path,
                        message=str(error),
                    )
                )
                signature = _from_schema(objects[key])

        issues += _value_issues(context, path, name, list(present[name]), signature)
    return issues


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
            code, message = 'TSV_COLUMN_MISSING', f'required initial column {target + 1} not found'
        elif index != target:
            code = 'TSV_COLUMN_ORDER_INCORRECT'
            message = f'initial column {target + 1} found at position {index + 1}'
        else:
            continue
        issues.append(
            coded_issue(
                context.schema,
                code,
                location=context.file.relative_path,
                sub_code=name,
                rule=path,
                message=f'{name}: {message}',
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
                coded_issue(
                    context.schema,
                    'TSV_INDEX_VALUE_NOT_UNIQUE',
                    location=context.file.relative_path,
                    rule=path,
                    message=f'row {row + 2}, value {value!r}',
                )
            )
        else:
            seen.add(value)
    return issues


# --- value types ----------------------------------------------------------


def _value_issues(
    context: Context, path: str, name: str, values: list[str], signature: Signature
) -> list[Issue]:
    """Report the first value of a column that breaks its signature.

    ``89+`` in an ``age`` column is the one exception: deprecated rather than wrong,
    and warned about once.
    """
    if _trivial(signature):
        return []
    pattern = signature.pattern
    if pattern is None:
        formats = context.schema['objects']['formats']
        if any(fmt not in formats.keys() for fmt in signature.formats):  # noqa: SIM118
            return []  # an unknown format: nothing to check against
        pattern = '|'.join(str(formats[fmt]['pattern']) for fmt in signature.formats)
    # Anchored the way the reference validator anchors it: "^" + pattern + "$",
    # without grouping the alternatives.
    compiled = re.compile(f'^{pattern}$')

    issues: list[Issue] = []
    age_warned = False
    for row, value in enumerate(values):
        if _fits(value, compiled, signature):
            continue
        if name == 'age' and value == '89+':
            if not age_warned:
                age_warned = True
                issues.append(
                    coded_issue(
                        context.schema,
                        'TSV_PSEUDO_AGE_DEPRECATED',
                        location=context.file.relative_path,
                        message=f'line {row + 2}',
                    )
                )
            continue
        hint = ", did you mean 'n/a'?" if re.fullmatch(r'\s*(NA|na|nan|NaN|n/a)\s*', value) else ''
        issues.append(
            coded_issue(
                context.schema,
                'TSV_VALUE_INCORRECT_TYPE',
                location=context.file.relative_path,
                sub_code=name,
                rule=path,
                message=f'line {row + 2}: {value!r}{hint}',
            )
        )
        break
    return issues


def _fits(value: str, pattern: re.Pattern[str], signature: Signature) -> bool:
    """Whether one cell satisfies the signature. ``n/a`` always does."""
    if value == 'n/a':
        return True
    if not pattern.search(value):
        return False
    if signature.levels is not None and value not in signature.levels:
        return False
    if signature.maximum is not None or signature.minimum is not None:
        number = _parse_float(value)
        if signature.maximum is not None and not number <= signature.maximum:
            return False
        if signature.minimum is not None and not number >= signature.minimum:
            return False
    return True


def _signature(column: Mapping[str, Any], definition: Mapping[str, Any] | None) -> Signature:
    """Return the signature of a listed column: the schema's, refined by the sidecar.

    A column whose schema object has a ``definition`` (a conventional column, such as
    ``trial_type``) is fully defined by the sidecar when the sidecar defines it.
    """
    if 'definition' in column.keys():  # noqa: SIM118
        return _from_definition(definition or column['definition'])
    base = _from_schema(column)
    return _refine(base, _from_definition(definition)) if definition is not None else base


def _from_schema(column: Mapping[str, Any]) -> Signature:
    """Return the signature the schema gives a column."""
    levels = column.get('enum')
    return Signature(
        formats=tuple(_formats(column)),
        pattern=column.get('pattern'),
        units=column.get('unit'),
        levels=tuple(str(level) for level in levels) if levels is not None else None,
        maximum=column.get('maximum'),
        minimum=column.get('minimum'),
    )


def _from_definition(definition: Mapping[str, Any]) -> Signature:
    """Return the signature a sidecar's column definition gives (``Format``, ``Levels`` ...)."""
    fmt = definition.get('Format') or ('number' if definition.get('Units') else 'string')
    levels = definition.get('Levels')
    return Signature(
        formats=(str(fmt),),
        units=definition.get('Units'),
        levels=tuple(str(level) for level in levels) if isinstance(levels, Mapping) else None,
        maximum=definition.get('Maximum'),
        minimum=definition.get('Minimum'),
    )


def _refine(base: Signature, override: Signature) -> Signature:
    """Combine the schema's signature with the sidecar's, which may only narrow it.

    Raises :class:`_Redefined` when the sidecar contradicts the schema: another kind
    of value (text where the schema wants numbers), levels outside the schema's,
    different units, or wider bounds.
    """
    kinds = {_kind(fmt) for fmt in base.formats}
    if _kind(override.formats[0]) not in kinds:
        raise _Redefined(f'format {override.formats[0]!r} must be {" or ".join(base.formats)}')
    levels = override.levels if override.levels is not None else base.levels
    if (
        base.levels is not None
        and override.levels is not None
        and not set(override.levels) <= set(base.levels)
    ):
        raise _Redefined(
            f'levels {{{", ".join(override.levels)}}} are not a subset of '
            f'{{{", ".join(base.levels)}}}'
        )
    units = override.units if override.units is not None else base.units
    if base.units is not None and units != base.units:
        raise _Redefined(f'unit {units!r} must be {base.units!r}')
    minimum = override.minimum if override.minimum is not None else base.minimum
    if base.minimum is not None and minimum is not None and minimum < base.minimum:
        raise _Redefined(f'minimum {minimum} is less than {base.minimum}')
    maximum = override.maximum if override.maximum is not None else base.maximum
    if base.maximum is not None and maximum is not None and maximum > base.maximum:
        raise _Redefined(f'maximum {maximum} is greater than {base.maximum}')
    return Signature(
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


def _trivial(signature: Signature) -> bool:
    """Whether every value would pass, so there is nothing to check."""
    return (
        signature.levels is None
        and signature.maximum is None
        and signature.minimum is None
        and (
            (signature.pattern is None and signature.formats[0] == 'string')
            or signature.pattern == '.*'
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
