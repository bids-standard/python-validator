"""The ``fields`` payload: required and recommended JSON fields, and the values they hold.

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
definition in ``schema.objects.metadata`` (:mod:`.values`); a wrong value
is ``JSON_SCHEMA_VALIDATION_ERROR``, reported on the JSON file that holds it, once.

This follows the reference validator's ``evalJsonCheck`` (``applyRules.ts``). The rule
engine (:mod:`.rules`) calls :func:`field_issues` for every rule with a ``fields``
payload whose selectors hold for the file.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..issues import Issue, IssueDefinition, Severity
from .values import value_errors

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from ..context import Context

# The names other modules are meant to import from this one.
__all__ = [
    'JSON_KEY_RECOMMENDED',
    'JSON_KEY_REQUIRED',
    'SIDECAR_KEY_RECOMMENDED',
    'SIDECAR_KEY_REQUIRED',
    'field_issues',
]

# --- what this module reports --------------------------------------------
#
# Defined by the schema, and read from it where they are reported:
#
#   JSON_SCHEMA_VALIDATION_ERROR   rules.errors.JsonSchemaValidationError
#   a field's own issue            the ``issue`` of a field in a rule, such as
#                                  B0_FIELD_IDENTIFIER_RECOMMENDED
#
# Defined only by the reference validator (bids-validator, src/issues/list.ts):

# A data file's sidecar lacks a required field.
SIDECAR_KEY_REQUIRED = IssueDefinition(
    'SIDECAR_KEY_REQUIRED',
    Severity.ERROR,
    "A data file's JSON sidecar is missing a key listed as required.",
)
# A data file's sidecar lacks a recommended field.
SIDECAR_KEY_RECOMMENDED = IssueDefinition(
    'SIDECAR_KEY_RECOMMENDED',
    Severity.WARNING,
    "A data file's JSON sidecar is missing a key listed as recommended.",
)
# A JSON file (such as dataset_description.json) lacks a required field.
JSON_KEY_REQUIRED = IssueDefinition(
    'JSON_KEY_REQUIRED', Severity.ERROR, 'A JSON file is missing a key listed as required.'
)
# A JSON file lacks a recommended field.
JSON_KEY_RECOMMENDED = IssueDefinition(
    'JSON_KEY_RECOMMENDED', Severity.WARNING, 'A JSON file is missing a key listed as recommended.'
)

# Extensions of files that cannot have a sidecar: a JSON file is one, and text files at
# the root (README, CHANGES, CITATION.cff ...) describe the dataset, not a recording.
_NO_SIDECAR_EXTENSIONS = frozenset({'.json', '', '.md', '.txt', '.rst', '.cff'})

# A requirement level, as a severity. Optional, prohibited and deprecated fields are
# never reported missing.
_LEVELS = {'required': Severity.ERROR, 'recommended': Severity.WARNING}

# A level addendum, "required if `Key` is `Value`": a field whose level depends on the
# value of another field. Captures the new level, the key and the value.
_LEVEL_ADDENDUM = re.compile(r'(required|recommended) if `(\w+)` is `(\w+)`')

# In a derivative dataset every field is optional, unless the rule says it is written for
# derivatives by carrying exactly this selector.
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
    if sidecar_rule and context.extension in _NO_SIDECAR_EXTENSIONS:
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
            severity = _missing_field_severity(requirement, context)
            if severity is None or (derivative and not written_for_derivatives):
                continue
            issues.append(
                _missing_field_issue(context, path, name, requirement, severity, sidecar_rule)
            )
            continue
        issues += _wrong_value_issues(
            context, path, name, data[name], definition, formats, sidecar_rule
        )
    return issues


def _missing_field_severity(requirement: Any, context: Context) -> Severity | None:
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
        found = _LEVEL_ADDENDUM.search(str(addendum))
        if found:
            level, key, value = found.groups()
            if context.sidecar.get(key) == value:
                severity = _LEVELS[level]
    return severity


def _missing_field_issue(
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
        definition = IssueDefinition.from_schema(own, severity=severity)
        return definition.make_issue(location, sub_code=name, rule=path)
    required = severity is Severity.ERROR
    if sidecar_rule:
        definition = SIDECAR_KEY_REQUIRED if required else SIDECAR_KEY_RECOMMENDED
    else:
        definition = JSON_KEY_REQUIRED if required else JSON_KEY_RECOMMENDED
    level = 'required' if required else 'recommended'
    return definition.make_issue(
        location, sub_code=name, rule=path, message=f'the {level} field {name!r} is missing'
    )


def _wrong_value_issues(
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
    problem, not one per recording. The dataset remembers which values it has checked,
    as the reference validator's does (``sidecarKeyValidated``).
    """
    if sidecar_rule:
        location = context.sidecar_origins.get(name, '')
        address = f'{location}:{name}'
        if address in context.dataset.checked_sidecar_values:
            return []
        context.dataset.checked_sidecar_values.add(address)
    else:
        location = context.file.relative_path
    problems = value_errors(value, definition, formats)
    if not problems:
        return []
    invalid = IssueDefinition.from_schema(
        context.schema['rules']['errors']['JsonSchemaValidationError']
    )
    return [
        invalid.make_issue(location, sub_code=name, rule=path, message=f'{name} {problem}')
        for problem in problems
    ]
