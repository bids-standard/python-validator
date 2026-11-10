"""Names and places: whether a file has a legal BIDS name, in a legal place.

Nothing here opens a file. The schema describes every legal filename in
``rules.files`` (which suffix goes in which datatype folder, which entities are
required or allowed, which extensions) and every legal folder in
``rules.directories`` (``sub-*``, ``ses-*``, a datatype, ``phenotype`` ...).

* :func:`folder_issues`: a folder only has to match a folder rule.
* :func:`filename_issues`: the filename rules the file's name matches are found first
  (:func:`.filename_rules.matching_filename_rules`), then the name is held to them. Each
  kind of failure has its own code, rather than a single blanket "bad name".

The checks follow the reference validator's ``filenameIdentify.ts``,
``filenameValidate.ts`` and ``filenameCase.ts``.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..issues import Issue, IssueDefinition, Severity
from .filename_rules import FilenameRule, matching_filename_rules
from .schema_cache import once_per_schema

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from ..context import Context

# The names other modules are meant to import from this one: the two checks
# (``checks.py`` runs them), the sidecar extensions, and the codes defined below.
__all__ = [
    'ALL_FILENAME_RULES_HAVE_ISSUES',
    'CASE_COLLISION',
    'DATATYPE_MISMATCH',
    'ENTITY_NOT_IN_RULE',
    'ENTITY_WITH_NO_LABEL',
    'EXTENSION_MISMATCH',
    'FILENAME_MISMATCH',
    'INVALID_ENTITY_LABEL',
    'INVALID_LOCATION',
    'MISSING_DATATYPE',
    'MISSING_REQUIRED_ENTITY',
    'SIDECAR_EXTENSIONS',
    'filename_issues',
    'folder_issues',
]

# --- what this module reports --------------------------------------------
#
# NOT_INCLUDED is defined by the schema (rules.errors.NotIncluded) and read from it
# where it is reported. The other codes are defined only by the reference validator
# (bids-validator, src/issues/list.ts), so they are written out here, once each, with
# its severity and wording. A check reports one with ``CODE.make_issue(location, ...)``.

# A name part with no label: ``acq-`` (nothing after the hyphen) or ``foo`` (no hyphen).
ENTITY_WITH_NO_LABEL = IssueDefinition(
    'ENTITY_WITH_NO_LABEL', Severity.ERROR, 'Found an entity with no label.'
)
# A label that breaks its entity's format: ``run-a`` (a run is a number).
INVALID_ENTITY_LABEL = IssueDefinition(
    'INVALID_ENTITY_LABEL',
    Severity.ERROR,
    "entity label doesn't match format found for files with this suffix",
)
# A required entity is missing: a ``_bold`` file with no ``task-``.
MISSING_REQUIRED_ENTITY = IssueDefinition(
    'MISSING_REQUIRED_ENTITY',
    Severity.ERROR,
    'Missing required entity for files with this suffix.',
)
# An entity this kind of file may not have: ``dir-`` on a ``_T1w``.
ENTITY_NOT_IN_RULE = IssueDefinition(
    'ENTITY_NOT_IN_RULE',
    Severity.ERROR,
    'Entity not listed as required or optional for files with this suffix',
)
# A data file not in any datatype folder: ``sub-01/sub-01_T1w.nii.gz``.
MISSING_DATATYPE = IssueDefinition(
    'MISSING_DATATYPE', Severity.ERROR, 'The file is not located in a datatype directory.'
)
# A data file in another datatype's folder: a ``_T1w`` in ``func/``.
DATATYPE_MISMATCH = IssueDefinition(
    'DATATYPE_MISMATCH',
    Severity.ERROR,
    'The datatype directory does not match datatype of found suffix and extension',
)
# An extension this kind of file may not have: ``_T1w.txt``.
EXTENSION_MISMATCH = IssueDefinition(
    'EXTENSION_MISMATCH',
    Severity.ERROR,
    'Extension used by file does not match allowed extensions for its suffix',
)
# A valid name under the wrong ``sub-``/``ses-`` folders.
INVALID_LOCATION = IssueDefinition(
    'INVALID_LOCATION',
    Severity.ERROR,
    'The file has a valid name, but is located in an invalid directory.',
)
# Entities out of the schema's order, or written twice.
FILENAME_MISMATCH = IssueDefinition(
    'FILENAME_MISMATCH',
    Severity.ERROR,
    'The filename is not formatted correctly. This could result from entity duplication '
    'or reordering.',
)
# Several filename rules match the name, and every one has a problem.
ALL_FILENAME_RULES_HAVE_ISSUES = IssueDefinition(
    'ALL_FILENAME_RULES_HAVE_ISSUES',
    Severity.ERROR,
    'Multiple filename rules were found as potential matches. All of them had at least '
    'one issue during filename validation.',
)
# Two files in one folder whose names differ only by letter case.
CASE_COLLISION = IssueDefinition(
    'CASE_COLLISION',
    Severity.ERROR,
    'Files with the same name but different casing have been found.',
)

# Extensions of files that describe data rather than hold it. They may sit above the
# data they describe (the inheritance principle), so the reference validator never
# asks them to be in a datatype folder (``sidecarExtensions`` in filenameValidate.ts).
SIDECAR_EXTENSIONS = frozenset({'.json', '.tsv', '.bvec', '.bval'})


def folder_issues(context: Context) -> list[Issue]:
    """Report a folder whose name matches no ``rules.directories`` rule.

    A rule matches by exact ``name`` (``phenotype``, ``docs``), by ``entity`` (a name
    starting with ``sub-`` or ``ses-``) or by ``value`` (any datatype: ``anat``,
    ``func`` ...), as in the reference's ``findDirRuleMatches``. Like the reference,
    this does not check how deep the folder sits.
    """
    schema = context.schema
    name = context.file.name
    kind = str(context.dataset.dataset_description.get('DatasetType', 'raw'))
    rules = schema['rules']['directories'].get(kind, {})
    for key in rules:
        rule = rules[key]
        if rule.get('name') == name:
            return []
        entity = rule.get('entity')
        if entity and name.startswith(f'{schema["objects"]["entities"][entity]["name"]}-'):
            return []
        value = rule.get('value')
        if value and name in schema['objects'].get(f'{value}s', {}).keys():  # noqa: SIM118
            return []
    return [_not_included(context)]


def filename_issues(context: Context) -> list[Issue]:
    """Return every name-and-place finding for one file.

    A directory recording (``sub-01_task-x_meg.ds/``) is checked as a file. Its
    extension carries a trailing slash (``.ds/``), which is exactly how the schema
    spells those extensions, so the ordinary rules apply to the folder's name.

    Letter case is checked whether or not the name is recognised: both spellings of a
    colliding pair are reported, as in the reference's separate ``filenameCase`` step.
    """
    return _name_issues(context, matching_filename_rules(context)) + _case_collision(context)


def _name_issues(context: Context, rules: tuple[FilenameRule, ...]) -> list[Issue]:
    """Hold the name to the rules that describe it."""
    if not rules:
        if context.file.relative_path == '.bidsignore':
            return []  # visited, but it is the ignore list, not part of the dataset
        return [_not_included(context)]

    entities = _entities(context, rules)
    issues: list[Issue] = []
    issues += _labels_missing(context, rules, entities)
    issues += _labels_malformed(context, entities)
    issues += _issues_against_rules(context, rules, entities)
    issues += _name_out_of_order(context, entities)
    return issues


def _not_included(context: Context) -> Issue:
    """Report a file or folder that is not part of BIDS, in the schema's words."""
    definition = IssueDefinition.from_schema(context.schema['rules']['errors']['NotIncluded'])
    return definition.make_issue(context.file.relative_path)


# --- the entities in the name ---------------------------------------------


def _entities(context: Context, rules: tuple[FilenameRule, ...]) -> dict[str, str]:
    """Return the entities to check, as the reference validator sees them.

    If no rule uses entities (``dataset_description.json``, ``README``), the file has
    none to check: the ``dataset`` in ``dataset_description`` is not an entity.
    Otherwise every key-label part of the name is one, and a part with no hyphen
    (``foo`` in ``sub-01_foo_T1w``) is an entity with no label, kept as ``''``.
    """
    if all(rule.entities is None for rule in rules):
        return {}
    return {key: value or '' for key, value in context.entities.items()}


def _labels_missing(
    context: Context, rules: tuple[FilenameRule, ...], entities: dict[str, str]
) -> list[Issue]:
    """``ENTITY_WITH_NO_LABEL``: ``acq-`` (empty), or ``foo`` (no hyphen at all)."""
    if all(rule.suffixes is None for rule in rules):
        return []
    empty = [key for key, label in entities.items() if not label]
    if not empty:
        return []
    return [
        ENTITY_WITH_NO_LABEL.make_issue(
            context.file.relative_path,
            sub_code=', '.join(empty),
            message=f'entities with no label: {", ".join(empty)}',
        )
    ]


def _labels_malformed(context: Context, entities: dict[str, str]) -> list[Issue]:
    """``INVALID_ENTITY_LABEL``: a label that breaks its entity's format (``run-a``)."""
    patterns = _label_patterns(context.schema)
    issues: list[Issue] = []
    for short, label in entities.items():
        pattern = patterns.get(short)
        if label and pattern and not re.fullmatch(pattern, label):
            issues.append(
                INVALID_ENTITY_LABEL.make_issue(
                    context.file.relative_path,
                    sub_code=short,
                    message=f'label {label!r} for entity {short!r} does not match /{pattern}/',
                )
            )
    return issues


def _name_out_of_order(context: Context, entities: dict[str, str]) -> list[Issue]:
    """``FILENAME_MISMATCH``: entities duplicated, or not in the schema's order."""
    if not entities:
        return []
    order = [short for short in _entity_order(context.schema) if short in entities]
    parts = [f'{short}-{entities[short]}' for short in order]
    # A directory recording's extension carries a trailing slash (``.ds/``) because that
    # is how the schema spells it, but the folder on disk is named without one. Drop it
    # so the rebuilt name is comparable, and readable in the message.
    extension = (context.extension or '').rstrip('/')
    expected = '_'.join([*parts, (context.suffix or '') + extension])
    if context.file.name == expected:
        return []
    return [
        FILENAME_MISMATCH.make_issue(
            context.file.relative_path, message=f'expected filename: {expected}'
        )
    ]


# --- the rules the name matched -------------------------------------------


def _issues_against_rules(
    context: Context, rules: tuple[FilenameRule, ...], entities: dict[str, str]
) -> list[Issue]:
    """Hold the file to its rule; with several candidates, to any one of them.

    With one candidate, its problems are reported directly. With several, the file is
    accepted if any candidate is satisfied; only when every candidate has a problem
    is ``ALL_FILENAME_RULES_HAVE_ISSUES`` reported.
    """
    if len(rules) == 1:
        return _issues_against_rule(context, rules[0], entities)
    if any(not _issues_against_rule(context, rule, entities) for rule in rules):
        return []
    return [
        ALL_FILENAME_RULES_HAVE_ISSUES.make_issue(
            context.file.relative_path,
            message='rules that matched with issues: ' + ', '.join(r.path for r in rules),
        )
    ]


def _issues_against_rule(
    context: Context, rule: FilenameRule, entities: dict[str, str]
) -> list[Issue]:
    """Entities, datatype folder, extension and place, against one rule."""
    issues: list[Issue] = []
    issues += _entities_against_rule(context, rule, entities)
    issues += _datatype_against_rule(context, rule)
    issues += _extension_against_rule(context, rule)
    issues += _location_issues(context, entities)
    return issues


def _entities_against_rule(
    context: Context, rule: FilenameRule, entities: dict[str, str]
) -> list[Issue]:
    """``MISSING_REQUIRED_ENTITY`` and ``ENTITY_NOT_IN_RULE``: too few, or too many."""
    if rule.entities is None:
        return []
    location = context.file.relative_path
    issues: list[Issue] = []
    # A file at the dataset root is a shared sidecar inherited downward, so it need not
    # carry the required entities. This mirrors the reference.
    missing = [entity for entity in rule.required_entities if entity not in entities]
    if missing and '/' in location:
        issues.append(
            MISSING_REQUIRED_ENTITY.make_issue(
                location,
                sub_code=', '.join(missing),
                message=f'missing required entities: {", ".join(missing)}',
                rule=rule.path,
            )
        )
    extra = [entity for entity in entities if entity not in rule.entities]
    if extra:
        issues.append(
            ENTITY_NOT_IN_RULE.make_issue(
                location,
                sub_code=', '.join(extra),
                message=f'entities not allowed for this file type: {", ".join(extra)}',
                rule=rule.path,
            )
        )
    return issues


def _datatype_against_rule(context: Context, rule: FilenameRule) -> list[Issue]:
    """``MISSING_DATATYPE`` and ``DATATYPE_MISMATCH``: not in a datatype folder, or the wrong one.

    Only for rules that name datatypes, and never for :data:`SIDECAR_EXTENSIONS`:
    a ``.json``, ``.tsv``, ``.bvec`` or ``.bval`` may sit above the data it describes.
    A file in a folder that is not a datatype at all (``sub-01/foo/``) is reported
    twice over: the folder as ``NOT_INCLUDED``, the file as ``MISSING_DATATYPE``.
    """
    if rule.datatypes is None or context.extension in SIDECAR_EXTENSIONS:
        return []
    allowed = ', '.join(rule.datatypes)
    if not context.datatype:
        return [
            MISSING_DATATYPE.make_issue(
                context.file.relative_path,
                message=f'the file is not in a datatype folder; expected one of: {allowed}',
                rule=rule.path,
            )
        ]
    if context.datatype not in rule.datatypes:
        return [
            DATATYPE_MISMATCH.make_issue(
                context.file.relative_path,
                message=f"the file is in '{context.datatype}'; its suffix belongs in: {allowed}",
                rule=rule.path,
            )
        ]
    return []


def _extension_against_rule(context: Context, rule: FilenameRule) -> list[Issue]:
    """``EXTENSION_MISMATCH``: an extension this kind of file may not have."""
    if rule.extensions is None or context.extension in rule.extensions:
        return []
    return [
        EXTENSION_MISMATCH.make_issue(
            context.file.relative_path,
            message=(
                f'extension {context.extension!r} is not allowed here; '
                f'allowed: {", ".join(rule.extensions)}'
            ),
            rule=rule.path,
        )
    ]


def _location_issues(context: Context, entities: dict[str, str]) -> list[Issue]:
    """``INVALID_LOCATION``: a valid name in the wrong folder.

    Two folder hierarchies are checked: ``sub-``/``ses-`` (raw data) and
    ``tpl-``/``cohort-`` (templates), each unless the name belongs to the other.
    """
    issues: list[Issue] = []
    if 'tpl' not in entities:
        issues += _location_issues_in(context, entities, 'sub', 'ses')
    if 'sub' not in entities:
        issues += _location_issues_in(context, entities, 'tpl', 'cohort')
    return issues


def _location_issues_in(
    context: Context, entities: dict[str, str], top: str, inner: str
) -> list[Issue]:
    """Check one hierarchy: ``top`` is ``sub`` or ``tpl``, ``inner`` is ``ses`` or ``cohort``.

    The file must be under the folders its own entities name, and must not be in such
    a folder without the matching entity in its name.
    """
    path = context.path
    top_label = entities.get(top)
    inner_label = entities.get(inner)
    problems: list[str] = []
    if top_label:
        expected = f'/{top}-{top_label}/'
        if inner_label:
            expected += f'{inner}-{inner_label}/'
        if not path.startswith(expected):
            problems.append(f'expected to be under {expected}')
    if not top_label and re.match(rf'^/{top}-', path):
        problems.append(f"in a '{top}-' folder but no '{top}' in the name")
    if not inner_label and re.search(rf'/{inner}-', path):
        problems.append(f"in a '{inner}-' folder but no '{inner}' in the name")
    return [
        INVALID_LOCATION.make_issue(
            context.file.relative_path,
            message=f'the file has a valid name but is in the wrong place ({problem})',
        )
        for problem in problems
    ]


# --- letter case ----------------------------------------------------------


def _case_collision(context: Context) -> list[Issue]:
    """``CASE_COLLISION``: other files in the folder whose names differ only by case.

    ``sub-01_T1w.nii.gz`` and ``sub-01_t1w.nii.gz`` are two files on Linux and one on
    a default macOS or Windows disk, so a dataset holding both cannot be copied
    safely. Only files are compared, as in the reference's ``filenameCase.ts``.
    """
    parent = context.file.parent
    if parent is None or context.file.is_dir:
        return []
    lowered = context.file.name.lower()
    others = [
        node.relative_path
        for name, node in parent.children.items()
        if not node.is_dir and name != context.file.name and name.lower() == lowered
    ]
    if not others:
        return []
    return [
        CASE_COLLISION.make_issue(
            context.file.relative_path,
            message='same name, different case: ' + ', '.join(others),
        )
    ]


# --- what the schema says about entities ----------------------------------


@once_per_schema
def _label_patterns(schema: Namespace) -> dict[str, str]:
    """Map each entity's short name (``run``) to the pattern its label must match.

    The schema gives each entity a ``format`` (``index``, ``label``), and each format
    a regular expression in ``objects.formats``.
    """
    formats = schema['objects'].get('formats', {})
    patterns: dict[str, str] = {}
    for entity in schema['objects']['entities'].values():
        name, fmt = entity.get('name'), entity.get('format')
        if name and fmt and str(fmt) in formats.keys():  # noqa: SIM118
            pattern = str(formats[str(fmt)].get('pattern', ''))
            if pattern:
                patterns[str(name)] = pattern
    return patterns


@once_per_schema
def _entity_order(schema: Namespace) -> list[str]:
    """Entity short names in the order the schema says they appear in a filename."""
    entities = schema['objects']['entities']
    order: list[str] = []
    for long_name in schema['rules'].get('entities', []):
        if long_name in entities.keys():  # noqa: SIM118
            name = entities[long_name].get('name')
            if name:
                order.append(str(name))
    return order
