"""Schema-driven filename and path validation, producing structured findings.

Scope: NAMES AND PLACES ONLY. Nothing here opens a file. What this module answers
is: given the schema's ``rules.files`` and ``rules.directories``, is this path a
legal BIDS name, in a legal place?

How it works: the schema describes every legal filename (which suffix goes in which
datatype folder, which entities are required or allowed, which extensions) and every
legal folder (``sub-*``, ``ses-*``, a datatype, ``phenotype`` ...). For each file this
module identifies the matching rule(s) and then checks the file against them,
emitting one specific code per kind of failure rather than a single blanket "bad
name". A folder only has to match a folder rule.

``NOT_INCLUDED`` is defined by the schema (``rules.errors.NotIncluded``). The other
codes come from the reference validator's catalog, mirrored in
:data:`bids_validator.issues.REFERENCE_CODES`. The checks follow the reference
validator's ``filenameIdentify.ts``, ``filenameValidate.ts`` and ``filenameCase.ts``.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from .issues import Issue, coded_issue
from .walk import is_directory

if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from .context import Context

__all__ = ['SIDECAR_EXTENSIONS', 'filename_issues', 'identified']

# Extensions of files that describe data rather than hold it. They may sit above the
# data they describe (the inheritance principle), so the reference validator never
# asks them to be in a datatype folder (``sidecarExtensions`` in filenameValidate.ts).
SIDECAR_EXTENSIONS = frozenset({'.json', '.tsv', '.bvec', '.bval'})

# Per-schema caches. Schema objects are cached for the process, so id() is stable.
_RULES_MEMO: dict[int, list[tuple[str, Mapping[str, Any]]]] = {}
_ENTITY_BY_SHORT_MEMO: dict[int, dict[str, Mapping[str, Any]]] = {}
_ORDERED_SHORT_MEMO: dict[int, list[str]] = {}

Rule = tuple[str, Mapping[str, Any]]  # (dotted schema path, rule)


def filename_issues(context: Context) -> list[Issue]:
    """Return every name-and-place finding for one file or folder.

    For a folder: does its name match a folder rule? For a file, three steps:

    1. Find which ``rules.files`` rule or rules the file matches. None means the file
       is not BIDS at all, reported as ``NOT_INCLUDED``.
    2. Narrow several matches down to the best candidate.
    3. Run each check family, concatenating the findings.

    A directory recording (``sub-01_task-x_meg.ds/``) is checked as a file. Its
    extension carries a trailing slash (``.ds/``), which is exactly how the schema
    spells those extensions, so the ordinary rules apply to the folder's name.
    """
    if is_directory(context):
        return _directory_issues(context)
    # Letter case is checked whether or not the name is recognised: both spellings of
    # a colliding pair are reported, as in the reference's separate filenameCase step.
    return _name_issues(context) + _case_collision(context)


def _name_issues(context: Context) -> list[Issue]:
    """Identify the file's rule(s), then run the rule checks on its name and place."""
    matched = _find_rule_matches(context)
    if not matched:
        if context.file.relative_path == '.bidsignore':
            return []  # visited, but it is the ignore list, not part of the dataset
        return [coded_issue(context.schema, 'NOT_INCLUDED', location=context.file.relative_path)]

    # Several rules can match one name; keep the best candidate(s).
    matched = _narrow(context, matched)
    entities = _entities(context, matched)

    # Each check returns a list, so the findings simply add up. The codes each one
    # can emit are named alongside it.
    issues: list[Issue] = []
    issues += _missing_label(context, matched, entities)  # ENTITY_WITH_NO_LABEL
    issues += _entity_label_check(context, entities)  # INVALID_ENTITY_LABEL
    issues += _check_rules(context, matched, entities)  # MISSING_REQUIRED_ENTITY,
    # ENTITY_NOT_IN_RULE, MISSING_DATATYPE, DATATYPE_MISMATCH, EXTENSION_MISMATCH,
    # INVALID_LOCATION, ALL_FILENAME_RULES_HAVE_ISSUES
    issues += _reconstruction_failure(context, entities)  # FILENAME_MISMATCH
    return issues


def identified(context: Context) -> Context:
    """Return the context as the schema rules see it, once its name is identified.

    A part of the name that no matched ``rules.files`` rule uses is cleared: a file
    that matched no rule at all (``NOT_INCLUDED``) has no entities, suffix or
    extension for the rules to read, and neither has a ``README`` entities. Without
    this, an unrecognised file such as ``.bidsignore`` would be held to the sidecar
    rules of whatever its name happens to resemble. This is the reference validator's
    ``cleanContext`` (``filenameIdentify.ts``).

    Returns the context itself when nothing is cleared, otherwise a read-only view of
    it: nothing is copied or loaded again, and the context is not changed.
    """
    matched = _narrow(context, _find_rule_matches(context))
    cleared: dict[str, Any] = {}
    for key, part, empty in (
        ('entities', 'entities', {}),
        ('extensions', 'extension', ''),
        ('suffixes', 'suffix', ''),
    ):
        if all(not node.get(key) for _path, node in matched):
            cleared[part] = empty
    if not cleared:
        return context
    return cast('Context', _Identified(context, cleared))


class _Identified:
    """A context with some name parts cleared; everything else is the context's own."""

    def __init__(self, context: Context, cleared: dict[str, Any]) -> None:
        self._context = context
        self._cleared = cleared

    def __getattr__(self, name: str) -> Any:
        if name in self._cleared:
            return self._cleared[name]
        return getattr(self._context, name)


# --- folders --------------------------------------------------------------


def _directory_issues(context: Context) -> list[Issue]:
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
        node = rules[key]
        if node.get('name') == name:
            return []
        entity = node.get('entity')
        if entity and name.startswith(f'{schema["objects"]["entities"][entity]["name"]}-'):
            return []
        value = node.get('value')
        if value and name in schema['objects'].get(f'{value}s', {}).keys():  # noqa: SIM118
            return []
    return [coded_issue(schema, 'NOT_INCLUDED', location=context.file.relative_path)]


# --- rule identification --------------------------------------------------


def _file_rules(schema: Namespace) -> list[Rule]:
    """Flatten ``rules.files`` to ``[(rule_path, leaf_rule)]``, once per schema."""
    cached = _RULES_MEMO.get(id(schema))
    if cached is not None:
        return cached
    out: list[Rule] = []
    files = schema['rules'].get('files', {})
    for group in files:
        _collect(files[group], f'rules.files.{group}', out)
    _RULES_MEMO[id(schema)] = out
    return out


def _collect(node: Any, path: str, out: list[Rule]) -> None:
    """Collect leaf rules under ``node`` into ``out`` as ``(dotted_path, rule)`` pairs.

    A node is a leaf when it carries ``path``, ``stem`` or ``suffixes``. Anything else is
    a grouping level to descend into.
    """
    if not isinstance(node, Mapping):
        return
    keys = node.keys()
    if 'path' in keys or 'stem' in keys or 'suffixes' in keys:
        out.append((path, node))
        return
    for key in keys:
        _collect(node[key], f'{path}.{key}', out)


def _find_rule_matches(context: Context) -> list[Rule]:
    """Return every ``rules.files`` rule the file matches.

    Derivative rules only apply to a derivative dataset. An empty result means the
    file is not BIDS at all, reported as ``NOT_INCLUDED``.
    """
    derivative = context.dataset.dataset_description.get('DatasetType') == 'derivative'
    return [
        (path, node)
        for path, node in _file_rules(context.schema)
        if (derivative or not path.startswith('rules.files.deriv'))
        and _rule_matches(node, context)
    ]


def _rule_matches(node: Mapping[str, Any], context: Context) -> bool:
    """Return whether one rule applies, by exact path, stem glob, or suffix.

    Suffix matching deliberately ignores the datatype, mirroring the reference
    validator, which is why a misplaced file still matches a rule.
    """
    if 'path' in node and '/' + str(node['path']) == context.path:
        return True
    if 'stem' in node and _match_stem(node, context):
        return True
    return 'suffixes' in node and context.suffix in list(node['suffixes'])


def _match_stem(node: Mapping[str, Any], context: Context) -> bool:
    """Return whether the file's stem matches the rule's glob, and its datatype if named.

    Used by fixed-name rules such as ``participants`` and ``*_scans``.
    """
    stem = context.file.name.split('.')[0]
    if not fnmatch.fnmatchcase(stem, str(node['stem'])):
        return False
    if 'datatypes' in node:
        return context.datatype in list(node['datatypes'])
    return True


def _narrow(context: Context, matched: list[Rule]) -> list[Rule]:
    """Prefer the rule sharing the file's datatype, then the one whose entities fit."""
    if len(matched) <= 1:
        return matched
    by_datatype = [
        (p, n) for p, n in matched if 'datatypes' in n and context.datatype in list(n['datatypes'])
    ]
    if by_datatype:
        matched = by_datatype
    if len(matched) <= 1:
        return matched
    by_ent_ext = [(p, n) for p, n in matched if _entities_extensions_fit(context, n)]
    return by_ent_ext or matched


def _entities_extensions_fit(context: Context, rule: Mapping[str, Any]) -> bool:
    """Return whether the extension is allowed and the entities fit within the rule.

    The second tie-breaker in :func:`_narrow`, used when the datatype did not settle it.
    """
    ext_ok = 'extensions' not in rule or context.extension in list(rule['extensions'])
    if 'entities' not in rule:
        return ext_ok
    rule_entities = {_short(context.schema, key) for key in rule['entities']}
    return ext_ok and set(context.entities).issubset(rule_entities)


# --- per-file checks ------------------------------------------------------


def _missing_label(context: Context, matched: list[Rule], entities: dict[str, str]) -> list[Issue]:
    """Report an entity with no label: ``acq-`` (empty) or ``foo`` (no hyphen at all)."""
    if not any('suffixes' in node for _path, node in matched):
        return []
    empty = [key for key, value in entities.items() if not value]
    if not empty:
        return []
    return [
        coded_issue(
            context.schema,
            'ENTITY_WITH_NO_LABEL',
            sub_code=', '.join(empty),
            location=context.file.relative_path,
            message=f'entities with no label: {", ".join(empty)}',
        )
    ]


def _entity_label_check(context: Context, entities: dict[str, str]) -> list[Issue]:
    """Report an entity label that breaks the schema format pattern."""
    schema = context.schema
    formats = schema['objects'].get('formats', {})
    by_short = _entity_by_short(schema)
    issues: list[Issue] = []
    for short, label in entities.items():
        if not label:
            continue  # reported as ENTITY_WITH_NO_LABEL instead
        definition = by_short.get(short)
        fmt = definition.get('format') if isinstance(definition, Mapping) else None
        if not fmt or str(fmt) not in formats:
            continue
        pattern = str(formats[str(fmt)].get('pattern', ''))
        if pattern and not re.fullmatch(pattern, label):
            issues.append(
                coded_issue(
                    schema,
                    'INVALID_ENTITY_LABEL',
                    sub_code=short,
                    location=context.file.relative_path,
                    message=f'label {label!r} for entity {short!r} does not match /{pattern}/',
                )
            )
    return issues


def _check_rules(context: Context, matched: list[Rule], entities: dict[str, str]) -> list[Issue]:
    """Check the file against the matched rule or rules and return the findings.

    With one candidate, report its problems directly. With several, accept the file if
    any candidate is satisfied cleanly; only when every candidate has a problem is
    ``ALL_FILENAME_RULES_HAVE_ISSUES`` reported.
    """
    if len(matched) == 1:
        return _rule_issues(context, matched[0], entities)
    per_rule = [_rule_issues(context, entry, entities) for entry in matched]
    if any(not issues for issues in per_rule):
        return []
    return [
        coded_issue(
            context.schema,
            'ALL_FILENAME_RULES_HAVE_ISSUES',
            location=context.file.relative_path,
            message='rules that matched with issues: ' + ', '.join(p for p, _n in matched),
        )
    ]


def _rule_issues(context: Context, matched: Rule, entities: dict[str, str]) -> list[Issue]:
    """Run the four rule-scoped checks for one candidate rule.

    Entities, datatype folder, extension, and placement within the subject or session
    hierarchy.
    """
    path, rule = matched
    issues: list[Issue] = []
    issues += _entity_rule_issues(context, path, rule, entities)
    issues += _datatype_issues(context, path, rule)
    issues += _extension_mismatch(context, path, rule)
    issues += _invalid_location(context, entities)
    return issues


def _entity_rule_issues(
    context: Context, path: str, rule: Mapping[str, Any], entities: dict[str, str]
) -> list[Issue]:
    """Too few (required missing) or too many (not allowed) entities."""
    if 'entities' not in rule:
        return []
    schema = context.schema
    location = context.file.relative_path
    rule_entities = [_short(schema, key) for key in rule['entities']]
    issues: list[Issue] = []

    # Required-entity checks do not apply to a file at the dataset root: it is a
    # shared sidecar inherited downward. This mirrors the reference.
    if '/' in location:
        required = [
            _short(schema, key) for key, level in rule['entities'].items() if level == 'required'
        ]
        missing = [entity for entity in required if entity not in entities]
        if missing:
            issues.append(
                coded_issue(
                    schema,
                    'MISSING_REQUIRED_ENTITY',
                    sub_code=', '.join(missing),
                    location=location,
                    message=f'missing required entities: {", ".join(missing)}',
                    rule=path,
                )
            )

    extra = [entity for entity in entities if entity not in rule_entities]
    if extra:
        issues.append(
            coded_issue(
                schema,
                'ENTITY_NOT_IN_RULE',
                sub_code=', '.join(extra),
                location=location,
                message=f'entities not allowed for this file type: {", ".join(extra)}',
                rule=path,
            )
        )
    return issues


def _datatype_issues(context: Context, path: str, rule: Mapping[str, Any]) -> list[Issue]:
    """Report a data file outside a datatype folder, or in the wrong one.

    Only for rules that name datatypes, and never for :data:`SIDECAR_EXTENSIONS`:
    a ``.json``, ``.tsv``, ``.bvec`` or ``.bval`` may sit above the data it describes.
    A file in a folder that is not a datatype at all (``sub-01/foo/``) is reported
    twice over: the folder as ``NOT_INCLUDED``, the file as ``MISSING_DATATYPE``.
    """
    if 'datatypes' not in rule or context.extension in SIDECAR_EXTENSIONS:
        return []
    allowed = ', '.join(str(d) for d in rule['datatypes'])
    if not context.datatype:
        return [
            coded_issue(
                context.schema,
                'MISSING_DATATYPE',
                location=context.file.relative_path,
                message=f'the file is not in a datatype folder; expected one of: {allowed}',
                rule=path,
            )
        ]
    if context.datatype not in list(rule['datatypes']):
        return [
            coded_issue(
                context.schema,
                'DATATYPE_MISMATCH',
                location=context.file.relative_path,
                message=f"the file is in '{context.datatype}'; its suffix belongs in: {allowed}",
                rule=path,
            )
        ]
    return []


def _extension_mismatch(context: Context, path: str, rule: Mapping[str, Any]) -> list[Issue]:
    """Report an extension that is not allowed for this suffix."""
    if 'extensions' in rule and context.extension not in list(rule['extensions']):
        allowed = ', '.join(str(e) for e in rule['extensions'])
        return [
            coded_issue(
                context.schema,
                'EXTENSION_MISMATCH',
                location=context.file.relative_path,
                message=f'extension {context.extension!r} is not allowed here; allowed: {allowed}',
                rule=path,
            )
        ]
    return []


def _invalid_location(context: Context, entities: dict[str, str]) -> list[Issue]:
    """Report a valid name that is in the wrong folder."""
    path = context.path
    issues: list[Issue] = []
    if 'tpl' not in entities:
        issues += _validate_location(entities, path, context, 'sub', 'ses')
    if 'sub' not in entities:
        issues += _validate_location(entities, path, context, 'tpl', 'cohort')
    return issues


def _validate_location(
    entities: Mapping[str, str], path: str, context: Context, top: str, sub: str
) -> list[Issue]:
    """Check one folder hierarchy for placement problems.

    ``top``/``sub`` is either ``sub``/``ses`` or ``tpl``/``cohort``. Reports when the
    file is not under the folders its own entities name, or when it sits in such a
    folder without the matching entity in its name.
    """
    issues: list[Issue] = []
    top_val = entities.get(top)
    sub_val = entities.get(sub)
    if top_val:
        expected = f'/{top}-{top_val}/'
        if sub_val:
            expected += f'{sub}-{sub_val}/'
        if not path.startswith(expected):
            issues.append(_location_issue(context, f'expected to be under {expected}'))
    if not top_val and re.match(rf'^/{top}-', path):
        issues.append(_location_issue(context, f"in a '{top}-' folder but no '{top}' in the name"))
    if not sub_val and re.search(rf'/{sub}-', path):
        issues.append(_location_issue(context, f"in a '{sub}-' folder but no '{sub}' in the name"))
    return issues


def _location_issue(context: Context, detail: str) -> Issue:
    """Build one ``INVALID_LOCATION`` finding, with ``detail`` explaining the placement."""
    return coded_issue(
        context.schema,
        'INVALID_LOCATION',
        location=context.file.relative_path,
        message=f'the file has a valid name but is in the wrong place ({detail})',
    )


def _reconstruction_failure(context: Context, entities: dict[str, str]) -> list[Issue]:
    """Entities duplicated or out of the schema's canonical order."""
    if not entities:
        return []
    ordered = [short for short in _ordered_short(context.schema) if short in entities]
    parts = [f'{short}-{entities[short]}' for short in ordered]
    # A directory recording's extension carries a trailing slash (``.ds/``) because that
    # is how the schema spells it, but the folder on disk is named without one. Drop it
    # so the rebuilt name is comparable, and readable in the message.
    extension = (context.extension or '').rstrip('/')
    expected = '_'.join([*parts, (context.suffix or '') + extension])
    if context.file.name != expected:
        return [
            coded_issue(
                context.schema,
                'FILENAME_MISMATCH',
                location=context.file.relative_path,
                message=f'expected filename: {expected}',
            )
        ]
    return []


def _case_collision(context: Context) -> list[Issue]:
    """Report other files in the same folder whose names differ only by letter case.

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
        coded_issue(
            context.schema,
            'CASE_COLLISION',
            location=context.file.relative_path,
            message='same name, different case: ' + ', '.join(others),
        )
    ]


# --- helpers --------------------------------------------------------------


def _entities(context: Context, matched: list[Rule]) -> dict[str, str]:
    """Return the entities to check, as the reference validator sees them.

    If no matched rule uses entities (``dataset_description.json``, ``README``), the
    file has none to check: the ``dataset`` in ``dataset_description`` is not an
    entity. Otherwise every key-label part of the name is one, and a part with no
    hyphen (``foo`` in ``sub-01_foo_T1w``) is an entity with no label, kept as ``''``.
    """
    if not any('entities' in node for _path, node in matched):
        return {}
    return {key: value or '' for key, value in context.entities.items()}


def _entity_by_short(schema: Namespace) -> dict[str, Mapping[str, Any]]:
    """Map entity short names to their schema definitions, memoised per schema.

    Filenames use short names such as ``acq`` while the schema keys entities by long
    name such as ``acquisition``, so this is the bridge between the two.
    """
    cached = _ENTITY_BY_SHORT_MEMO.get(id(schema))
    if cached is not None:
        return cached
    out: dict[str, Mapping[str, Any]] = {}
    for definition in schema['objects']['entities'].values():
        name = definition.get('name')
        if name:
            out[str(name)] = definition
    _ENTITY_BY_SHORT_MEMO[id(schema)] = out
    return out


def _ordered_short(schema: Namespace) -> list[str]:
    """Entity short names in the schema's canonical filename order."""
    cached = _ORDERED_SHORT_MEMO.get(id(schema))
    if cached is not None:
        return cached
    entities = schema['objects']['entities']
    out: list[str] = []
    for long_name in schema['rules'].get('entities', []):
        if long_name in entities.keys():  # noqa: SIM118
            name = entities[long_name].get('name')
            if name:
                out.append(str(name))
    _ORDERED_SHORT_MEMO[id(schema)] = out
    return out


def _short(schema: Namespace, long_name: str) -> str:
    """Convert an entity's long schema name to the short form used in filenames."""
    entities = schema['objects']['entities']
    if long_name in entities.keys():  # noqa: SIM118
        return str(entities[long_name].get('name', long_name))
    return long_name
