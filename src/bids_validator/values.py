"""Check a metadata value against its schema definition.

Every metadata field in ``schema.objects.metadata`` comes with a small JSON Schema:
``RepetitionTime`` must be a number greater than 0, ``Authors`` an array of strings,
``DatasetType`` one of three words. :func:`value_errors` checks one value against one
such definition and returns what is wrong, as messages; an empty list means valid.

The reference validator does this with the ajv library, the schema's
``objects.formats`` patterns registered as ajv formats. This module implements the
part of JSON Schema those definitions use, with ajv's behaviour, so the findings
match:

* **One error per value.** ajv stops at the first keyword that fails (its default,
  ``allErrors: false``), checking ``type`` first, then the keywords for any type
  (``enum``, ``anyOf``), then those for numbers, strings, arrays and objects.
* **``anyOf`` reports every branch.** When no alternative fits, each alternative's
  first error is reported, then ``must match a schema in anyOf``.
* **Formats are searched, not matched.** ajv tests a format's pattern anywhere in the
  string (``RegExp.test``), so a pattern without ``^``/``$`` only needs to occur
  somewhere. Several BIDS formats are written that way and accept almost anything
  in the reference validator; this module accepts the same.
* **Messages are ajv's** (``must be number``, ``must be >= 0`` ...), prefixed with the
  position inside the value when the problem is nested (``/0 must be string``).
"""

from __future__ import annotations

import math
import operator
import re
from collections.abc import Callable, Mapping
from typing import Any, TypeGuard

__all__ = ['json_equal', 'value_errors']

_COMPARISONS: tuple[tuple[str, str, Callable[[float, float], bool]], ...] = (
    ('maximum', '<=', operator.le),
    ('minimum', '>=', operator.ge),
    ('exclusiveMaximum', '<', operator.lt),
    ('exclusiveMinimum', '>', operator.gt),
)


def value_errors(value: Any, definition: Any, formats: Mapping[str, Any]) -> list[str]:
    """Return what is wrong with ``value`` according to ``definition``.

    Parameters
    ----------
    value : Any
        A value read from a JSON file.
    definition : Mapping
        Its schema definition, such as ``schema.objects.metadata.RepetitionTime``.
    formats : Mapping
        ``schema.objects.formats``: format name to ``{pattern: ...}``.

    Returns
    -------
    list of str
        ajv-style messages; empty when the value is valid.

    """
    return _errors(value, definition, formats, '')


def _errors(value: Any, schema: Any, formats: Mapping[str, Any], at: str) -> list[str]:
    """Return the errors of one value at one position, in ajv's keyword order."""
    if not isinstance(schema, Mapping):
        return []

    expected = schema.get('type')
    if expected is not None and not _has_type(value, expected):
        names = ','.join(expected) if isinstance(expected, list) else str(expected)
        return [_at(at, f'must be {names}')]

    if 'enum' in schema.keys() and not any(json_equal(value, option) for option in schema['enum']):  # noqa: SIM118
        return [_at(at, 'must be equal to one of the allowed values')]

    alternatives = schema.get('anyOf')
    if isinstance(alternatives, list):
        branches = [_errors(value, alternative, formats, at) for alternative in alternatives]
        if all(branches):
            return [errors[0] for errors in branches] + [_at(at, 'must match a schema in anyOf')]

    if _is_number(value):
        for keyword, sign, holds in _COMPARISONS:
            limit = schema.get(keyword)
            if _is_number(limit) and not holds(value, limit):
                return [_at(at, f'must be {sign} {limit}')]

    if isinstance(value, str):
        name = schema.get('format')
        pattern = formats.get(name, {}).get('pattern') if name else None
        if pattern is not None and re.search(str(pattern), value) is None:
            return [_at(at, f'must match format "{name}"')]

    if isinstance(value, list):
        return _array_errors(value, schema, formats, at)

    if isinstance(value, Mapping):
        return _object_errors(value, schema, formats, at)

    return []


def _array_errors(
    value: list[Any], schema: Mapping[str, Any], formats: Mapping[str, Any], at: str
) -> list[str]:
    if _is_number(schema.get('maxItems')) and len(value) > schema['maxItems']:
        return [_at(at, f'must NOT have more than {schema["maxItems"]} items')]
    if _is_number(schema.get('minItems')) and len(value) < schema['minItems']:
        return [_at(at, f'must NOT have fewer than {schema["minItems"]} items')]
    items = schema.get('items')
    if isinstance(items, Mapping):
        for index, item in enumerate(value):
            errors = _errors(item, items, formats, f'{at}/{index}')
            if errors:
                return errors
    return []


def _object_errors(
    value: Mapping[str, Any], schema: Mapping[str, Any], formats: Mapping[str, Any], at: str
) -> list[str]:
    for name in schema.get('required', []) or []:
        if name not in value:
            return [_at(at, f"must have required property '{name}'")]
    properties = schema.get('properties') or {}
    if schema.get('additionalProperties') is False and any(
        key not in properties.keys()  # noqa: SIM118
        for key in value
    ):
        return [_at(at, 'must NOT have additional properties')]
    for name in properties.keys():  # noqa: SIM118
        if name in value:
            errors = _errors(value[name], properties[name], formats, f'{at}/{name}')
            if errors:
                return errors
    return []


def _has_type(value: Any, expected: Any) -> bool:
    """Whether ``value`` has the JSON type ``expected`` (a name or a list of names)."""
    if isinstance(expected, list):
        return any(_has_type(value, name) for name in expected)
    match expected:
        case 'number':
            return _is_number(value)
        case 'integer':
            return _is_number(value) and float(value).is_integer()
        case 'string':
            return isinstance(value, str)
        case 'boolean':
            return isinstance(value, bool)
        case 'array':
            return isinstance(value, list)
        case 'object':
            return isinstance(value, Mapping)
        case 'null':
            return value is None
    return True  # an unknown type name: do not flag


def _is_number(value: Any) -> TypeGuard[int | float]:
    """Return whether a value is a JSON number: int or float, not bool (True counts as 1)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def json_equal(value: Any, option: Any) -> bool:
    """JSON equality: ``true`` is not ``1``, and arrays and objects compare by content."""
    if isinstance(value, bool) or isinstance(option, bool):
        return isinstance(value, bool) and isinstance(option, bool) and value == option
    if _is_number(value) and _is_number(option):
        return float(value) == float(option)
    if isinstance(value, list) and isinstance(option, list):
        return len(value) == len(option) and all(map(json_equal, value, option))
    if isinstance(value, Mapping) and isinstance(option, Mapping):
        return value.keys() == option.keys() and all(
            json_equal(value[k], option[k]) for k in value
        )
    return type(value) is type(option) and bool(value == option)


def _at(at: str, message: str) -> str:
    """Prefix a message with the position inside the value, when there is one."""
    return f'{at} {message}' if at else message
