"""JSON metadata: required and recommended fields, the values they hold, and overrides.

Three schema rule groups list the fields a JSON file should hold, as a ``fields``
payload::

    MRIFuncRepetitionTime:            # rules.sidecars.mri.MRIFuncRepetitionTime
      selectors:
        - modality == "mri"
        - datatype == "func"
        - '!("VolumeTiming" in sidecar)'
      fields:
        RepetitionTime:
          level: required

* ``rules.sidecars`` describe the SIDECAR of a data file: the JSON fields that apply
  to it after the inheritance principle has merged its JSON files
  (``context.sidecar``). A missing field is ``SIDECAR_KEY_REQUIRED`` or
  ``SIDECAR_KEY_RECOMMENDED``, reported on the data file.
* ``rules.json`` and ``rules.dataset_metadata`` describe one JSON file itself
  (``context.json``), such as ``dataset_description.json``. A missing field is
  ``JSON_KEY_REQUIRED`` or ``JSON_KEY_RECOMMENDED``.

A field may carry its own ``issue`` (``B0_FIELD_IDENTIFIER_RECOMMENDED``), used instead
of those generic codes. A field that IS present has its value checked against its
definition in ``schema.objects.metadata`` (:mod:`bids_validator.values`); a wrong value
is ``JSON_SCHEMA_VALIDATION_ERROR``, reported on the JSON file that holds it, once.

Separately, :func:`inheritance_issues` warns when a JSON file deeper in the tree gives
a field a different value than a JSON file above it (``SIDECAR_FIELD_OVERRIDE``).

All of this follows the reference validator's ``evalJsonCheck`` (``applyRules.ts``)
and ``loadSidecar`` (``schema/context.ts``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .context import ValidationError, load_json, sidecar_origins, walk_back
from .issues import Issue, Severity, coded_issue, schema_issue
from .types.files import FileTree
from .values import json_equal, value_errors
from .walk import is_directory

if TYPE_CHECKING:
    from .context import Context

__all__ = ['field_issues', 'inheritance_issues']

# Files that cannot have a sidecar: a JSON file is one, and text files at the root
# (README, CHANGES, CITATION.cff ...) describe the dataset, not a recording.
_NO_SIDECAR = frozenset({'.json', '', '.md', '.txt', '.rst', '.cff'})

# A requirement level, as a severity. Optional, prohibited and deprecated fields are
# never reported missing.
_LEVELS = {'required': Severity.ERROR, 'recommended': Severity.WARNING}

# "required if `Key` is `Value`": a field whose level depends on another field.
_ADDENDUM = re.compile(r'(required|recommended) if `(\w+)` is `(\w+)`')

# Derivatives make every field optional unless a rule is written for derivatives.
_DERIVATIVE_SELECTOR = 'dataset.dataset_description.DatasetType == "derivative"'


def field_issues(path: str, rule: Mapping[str, Any], context: Context) -> list[Issue]:
    """Payload ``fields``: report missing fields and wrong values.

    Parameters
    ----------
    path : str
        Dotted schema path of the rule (``rules.sidecars.mri.MRIHardware``).
    rule : Mapping
        The rule; its selectors already hold for this file.
    context : Context
        Everything known about one file.

    Returns
    -------
    list of Issue
        The findings.

    """
    sidecar_rule = path.startswith('rules.sidecars')
    if sidecar_rule and context.extension in _NO_SIDECAR:
        return []
    data: Mapping[str, Any] = (context.sidecar if sidecar_rule else context.json) or {}
    schema = context.schema
    metadata = schema['objects']['metadata']
    formats = schema['objects'].get('formats', {})
    derivative = context.dataset.dataset_description.get('DatasetType') == 'derivative'
    written_for_derivatives = _DERIVATIVE_SELECTOR in rule.get('selectors', [])

    issues: list[Issue] = []
    for key, requirement in rule['fields'].items():
        definition = metadata[key]
        name = str(definition['name'])
        if name not in data:
            severity = _severity(requirement, context)
            if severity is None or (derivative and not written_for_derivatives):
                continue
            issues.append(_missing(context, path, name, requirement, severity, sidecar_rule))
            continue
        issues += _wrong_value(context, path, name, data[name], definition, formats, sidecar_rule)
    return issues


def inheritance_issues(context: Context) -> list[Issue]:
    """Warn where a deeper JSON file changes a value set by a JSON file above it.

    The deeper value is the one that applies (that is the inheritance principle),
    but a dataset that sets a field twice to different values is usually a mistake.
    Reported on the deeper file, once per data file that inherits both. Values are
    compared by content, so the same list written twice is not an override.
    """
    if is_directory(context) or context.extension == '.json':
        return []
    try:
        chain = list(walk_back(context.file, inherit=True))
    except ValidationError:
        return []  # ambiguous: reported by the integrity checks
    applied: dict[str, Any] = {}
    origin: dict[str, str] = {}
    issues: list[Issue] = []
    for json in chain:  # nearest first
        if not isinstance(json, FileTree):
            continue  # only a search for several targets yields lists
        try:
            contents = load_json(json)
        except ValidationError:
            continue
        for key, value in contents.items():
            if key not in applied:
                applied[key] = value
                origin[key] = json.relative_path
            elif not json_equal(applied[key], value):
                issues.append(
                    coded_issue(
                        context.schema,
                        'SIDECAR_FIELD_OVERRIDE',
                        sub_code=key,
                        location=origin[key],
                        message=(
                            f'{key} = {applied[key]!r} overrides {value!r} '
                            f'from {json.relative_path}'
                        ),
                    )
                )
    return issues


def _severity(requirement: Any, context: Context) -> Severity | None:
    """Return the severity of a missing field, or None when it need not be reported.

    A requirement is a level (``"recommended"``) or ``{level: ..., level_addendum:
    ...}``. An addendum of the form "required if `Key` is `Value`" raises the level
    when the sidecar's ``Key`` is exactly the string ``Value``.
    """
    if isinstance(requirement, str):
        return _LEVELS.get(requirement)
    if not isinstance(requirement, Mapping):
        return None
    severity = _LEVELS.get(str(requirement.get('level')))
    addendum = requirement.get('level_addendum')
    if addendum:
        found = _ADDENDUM.search(str(addendum))
        if found:
            level, key, value = found.groups()
            if context.sidecar.get(key) == value:
                severity = _LEVELS[level]
    return severity


def _missing(
    context: Context,
    path: str,
    name: str,
    requirement: Any,
    severity: Severity,
    sidecar_rule: bool,
) -> Issue:
    """Build the finding for a missing field: the field's own issue, or the generic code."""
    location = context.file.relative_path
    own = requirement.get('issue') if isinstance(requirement, Mapping) else None
    if isinstance(own, Mapping) and own.get('code') and own.get('message'):
        return schema_issue(own, location=location, severity=severity, sub_code=name, rule=path)
    kind = 'SIDECAR_KEY' if sidecar_rule else 'JSON_KEY'
    level = 'REQUIRED' if severity is Severity.ERROR else 'RECOMMENDED'
    return coded_issue(
        context.schema,
        f'{kind}_{level}',
        location=location,
        sub_code=name,
        rule=path,
        message=f'the {level.lower()} field {name!r} is missing',
    )


def _wrong_value(
    context: Context,
    path: str,
    name: str,
    value: Any,
    definition: Mapping[str, Any],
    formats: Mapping[str, Any],
    sidecar_rule: bool,
) -> list[Issue]:
    """Return the findings for a present value that breaks its definition.

    A sidecar value is reported on the JSON file it came from, and only the first time
    any data file brings it up: a wrong value in a JSON at the dataset root is one
    problem, not one per recording.
    """
    if sidecar_rule:
        location = sidecar_origins(context.file).get(name, '')
        address = f'{location}:{name}'
        if address in context.dataset.checked_sidecar_values:
            return []
        context.dataset.checked_sidecar_values.add(address)
    else:
        location = context.file.relative_path
    return [
        coded_issue(
            context.schema,
            'JSON_SCHEMA_VALIDATION_ERROR',
            location=location,
            sub_code=name,
            rule=path,
            message=f'{name} {problem}',
        )
        for problem in value_errors(value, definition, formats)
    ]
