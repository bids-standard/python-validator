"""Schema-driven filename and path validation, producing structured findings.

Scope: NAMES AND PATHS ONLY. Nothing here opens a file or reads its contents, so
there are no empty-file, header, gzip, JSON, or tabular checks. Those belong to the
later content-validation layer. What this module answers is: given the schema's
``rules.files``, is this path a legal BIDS name, in a legal place?

How it works: the schema describes every legal filename (which suffix goes in which
datatype folder, which entities are required or allowed, which extensions). For each
file this module identifies the matching rule(s) and then checks the file against
them, emitting one specific code per kind of failure rather than a single blanket
"bad name".

The codes are the reference (Deno) ``bids-validator`` catalog, defined in its
``src/issues/list.ts``. They are deliberately NOT in the BIDS schema: the schema
supplies the rules a name is matched against, but it does not name these structural
failures. :data:`FILENAME_ISSUES` mirrors that catalog so the provenance is explicit
and the output stays interchangeable with the reference.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from bidsschematools.types.namespace import Namespace

from .bidsignore import Ignore, IgnoreMany
from .context import Context, Dataset
from .issues import DatasetIssues, Issue, Severity

if TYPE_CHECKING:
    from .bidsignore import HasMatch
    from .types.files import FileTree

__all__ = [
    'DEFAULT_IGNORES',
    'FILENAME_ISSUES',
    'collect_filename_issues',
    'filename_issues',
    'iter_contexts',
]

# Paths the reference validator never name-checks, from its ``src/files/ignore.ts``.
# ``.*`` covers dotfiles such as ``.DS_Store`` and ``.bidsignore`` itself; the named
# directories hold files BIDS does not constrain.
DEFAULT_IGNORES = ('.git**', '.*', 'sourcedata/', 'code/', 'stimuli/', 'log/')

# Extensions the BIDS inheritance principle allows to sit higher in the tree than the
# data they describe, so they are exempt from the datatype-directory requirement.
INHERITABLE_EXTENSIONS = frozenset({'.json', '.tsv'})

# The filename/path codes this module can emit, with the reference validator's
# reason text. Every one is an error; the reference defines no filename warnings.
FILENAME_ISSUES: dict[str, str] = {
    'NOT_INCLUDED': 'Files with such naming scheme are not part of BIDS specification.',
    'ENTITY_WITH_NO_LABEL': 'Found an entity with no label.',
    'INVALID_ENTITY_LABEL': ("entity label doesn't match format found for files with this suffix"),
    'MISSING_REQUIRED_ENTITY': 'Missing required entity for files with this suffix.',
    'ENTITY_NOT_IN_RULE': ('Entity not listed as required or optional for files with this suffix'),
    'DATATYPE_MISMATCH': (
        'The datatype directory does not match datatype of found suffix and extension'
    ),
    'EXTENSION_MISMATCH': (
        'Extension used by file does not match allowed extensions for its suffix'
    ),
    'INVALID_LOCATION': 'The file has a valid name, but is located in an invalid directory.',
    'FILENAME_MISMATCH': (
        'The filename is not formatted correctly. This could result from entity '
        'duplication or reordering.'
    ),
    'ALL_FILENAME_RULES_HAVE_ISSUES': (
        'Multiple filename rules were found as potential matches. All of them had at '
        'least one issue during filename validation.'
    ),
}

# Per-schema caches. Schema objects are cached for the process, so id() is stable.
_RULES_MEMO: dict[int, list[tuple[str, Mapping[str, Any]]]] = {}
_ENTITY_BY_SHORT_MEMO: dict[int, dict[str, Mapping[str, Any]]] = {}
_ORDERED_SHORT_MEMO: dict[int, list[str]] = {}
_DIR_RECORDING_MEMO: dict[int, set[str]] = {}


# --- public API -----------------------------------------------------------


def collect_filename_issues(tree: FileTree, schema: Namespace) -> DatasetIssues:
    """Validate every filename in a dataset tree.

    Parameters
    ----------
    tree : FileTree
        The dataset root, from ``FileTree.read_from_filesystem(root)``.
    schema : Namespace
        The BIDS schema to validate against.

    Returns
    -------
    DatasetIssues
        Every filename/path finding, in tree order.

    """
    dataset = Dataset(tree, schema)
    issues = DatasetIssues()
    for context in iter_contexts(dataset):
        issues.extend(filename_issues(context))
    return issues


def iter_contexts(dataset: Dataset, ignore: HasMatch | None = None) -> Iterator[Context]:
    """Yield a :class:`~bids_validator.context.Context` for every validatable file.

    Skips anything the dataset's ``.bidsignore`` or :data:`DEFAULT_IGNORES` match.
    Directory recordings (CTF ``.ds``, MEF ``.mefd``, OME-Zarr ...) are single units:
    the walk does not descend into them, so their internal files are not name-checked
    individually.
    """
    if ignore is None:
        ignore = build_ignore(dataset.tree)
    recordings = _directory_recordings(dataset.schema)
    yield from _walk(dataset.tree, dataset, recordings, ignore)


def build_ignore(tree: FileTree) -> IgnoreMany:
    """Build the ignore matcher: the reference defaults plus the dataset's .bidsignore."""
    ignores = [Ignore(list(DEFAULT_IGNORES))]
    bidsignore = tree.children.get('.bidsignore')
    if bidsignore is not None:
        ignores.append(Ignore.from_file(bidsignore))
    return IgnoreMany(ignores)


def filename_issues(context: Context) -> list[Issue]:
    """Return every filename/path finding for one file.

    Identifies the ``rules.files`` rule(s) the file matches, then checks it against
    them. An unmatched file is ``NOT_INCLUDED``; a matched one is checked for entity,
    datatype, extension, location, and ordering problems.
    """
    schema = context.schema
    relpath = context.file.relative_path

    # A directory recording is a unit, not a name to parse.
    if any(context.file.name.endswith(ext) for ext in _directory_recordings(schema)):
        return []

    matched = _find_rule_matches(schema, context)
    if not matched:
        return [
            Issue(
                code='NOT_INCLUDED',
                severity=Severity.ERROR,
                location=relpath,
                message=f'{context.file.name} does not match any BIDS naming rule',
            )
        ]

    matched = _narrow(schema, context, matched)
    issues: list[Issue] = []
    issues += _missing_label(context, matched)
    issues += _entity_label_check(schema, context)
    issues += _check_rules(schema, context, matched)
    issues += _missing_datatype_directory(context, matched)
    issues += _reconstruction_failure(schema, context)
    return issues


# --- walking --------------------------------------------------------------


def _walk(
    tree: FileTree, dataset: Dataset, recordings: set[str], ignore: HasMatch
) -> Iterator[Context]:
    for child in tree.children.values():
        if ignore.match(child.relative_path):
            continue
        if child.is_dir:
            if any(child.name.endswith(ext) for ext in recordings):
                continue  # a directory recording: do not descend
            yield from _walk(child, dataset, recordings, ignore)
        else:
            yield Context(child, dataset, None)


# --- rule identification --------------------------------------------------


def _file_rules(schema: Namespace) -> list[tuple[str, Mapping[str, Any]]]:
    """Flatten ``rules.files`` to ``[(rule_path, leaf_rule)]``, once per schema."""
    cached = _RULES_MEMO.get(id(schema))
    if cached is not None:
        return cached
    out: list[tuple[str, Mapping[str, Any]]] = []
    files = schema['rules'].get('files', {})
    for group in files:
        _collect(files[group], f'rules.files.{group}', out)
    _RULES_MEMO[id(schema)] = out
    return out


def _collect(node: Any, path: str, out: list[tuple[str, Mapping[str, Any]]]) -> None:
    if not _is_mapping(node):
        return
    if 'path' in node or 'stem' in node or 'suffixes' in node:
        out.append((path, node))
        return
    for key in node:
        _collect(node[key], f'{path}.{key}', out)


def _find_rule_matches(schema: Namespace, context: Context) -> list[tuple[str, Mapping[str, Any]]]:
    dataset_type = _dataset_type(context)
    out: list[tuple[str, Mapping[str, Any]]] = []
    for path, node in _file_rules(schema):
        # Derivative rules only apply to a derivative dataset.
        if path.startswith('rules.files.deriv') and dataset_type != 'derivative':
            continue
        if _rule_matches(node, context):
            out.append((path, node))
    return out


def _rule_matches(node: Mapping[str, Any], context: Context) -> bool:
    if 'path' in node and '/' + str(node['path']) == context.path:
        return True
    if 'stem' in node and _match_stem(node, context):
        return True
    return 'suffixes' in node and context.suffix in list(node['suffixes'])


def _match_stem(node: Mapping[str, Any], context: Context) -> bool:
    stem = context.file.name.split('.')[0]
    if not fnmatch.fnmatchcase(stem, str(node['stem'])):
        return False
    if 'datatypes' in node:
        return context.datatype in list(node['datatypes'])
    return True


def _narrow(
    schema: Namespace, context: Context, matched: list[tuple[str, Mapping[str, Any]]]
) -> list[tuple[str, Mapping[str, Any]]]:
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
    by_ent_ext = [(p, n) for p, n in matched if _entities_extensions_fit(schema, context, n)]
    return by_ent_ext or matched


def _entities_extensions_fit(schema: Namespace, context: Context, rule: Mapping[str, Any]) -> bool:
    ext_ok = 'extensions' not in rule or context.extension in list(rule['extensions'])
    if 'entities' not in rule:
        return ext_ok
    rule_entities = {_short(schema, key) for key in rule['entities']}
    return ext_ok and set(_entities(context)).issubset(rule_entities)


# --- per-file checks ------------------------------------------------------


def _missing_label(context: Context, matched: list[tuple[str, Mapping[str, Any]]]) -> list[Issue]:
    """Report an entity that is present with no label, e.g. ``acq-``."""
    if not any('suffixes' in node for _path, node in matched):
        return []
    empty = [key for key, value in _entities(context).items() if value == '']
    if not empty:
        return []
    return [
        Issue(
            code='ENTITY_WITH_NO_LABEL',
            sub_code=', '.join(empty),
            severity=Severity.ERROR,
            location=context.file.relative_path,
            message=f'entities with no label: {", ".join(empty)}',
        )
    ]


def _entity_label_check(schema: Namespace, context: Context) -> list[Issue]:
    """Report an entity label that breaks the schema format pattern."""
    formats = schema['objects'].get('formats', {})
    by_short = _entity_by_short(schema)
    issues: list[Issue] = []
    for short, label in _entities(context).items():
        if label == '':
            continue  # reported as ENTITY_WITH_NO_LABEL instead
        definition = by_short.get(short)
        fmt = definition.get('format') if isinstance(definition, Mapping) else None
        if not fmt or str(fmt) not in formats:
            continue
        pattern = str(formats[str(fmt)].get('pattern', ''))
        if pattern and not re.fullmatch(pattern, label):
            issues.append(
                Issue(
                    code='INVALID_ENTITY_LABEL',
                    sub_code=short,
                    severity=Severity.ERROR,
                    location=context.file.relative_path,
                    message=f'label {label!r} for entity {short!r} does not match /{pattern}/',
                )
            )
    return issues


def _check_rules(
    schema: Namespace, context: Context, matched: list[tuple[str, Mapping[str, Any]]]
) -> list[Issue]:
    if len(matched) == 1:
        return _rule_issues(schema, context, matched[0])
    # Several rules still match: if any matches cleanly, accept it; otherwise report
    # that every candidate had a problem.
    per_rule = [_rule_issues(schema, context, entry) for entry in matched]
    if any(not issues for issues in per_rule):
        return []
    return [
        Issue(
            code='ALL_FILENAME_RULES_HAVE_ISSUES',
            severity=Severity.ERROR,
            location=context.file.relative_path,
            message='the file resembles several BIDS rules but fully satisfies none of them',
        )
    ]


def _rule_issues(
    schema: Namespace, context: Context, matched: tuple[str, Mapping[str, Any]]
) -> list[Issue]:
    path, rule = matched
    issues: list[Issue] = []
    issues += _entity_rule_issues(schema, context, path, rule)
    issues += _datatype_mismatch(context, path, rule)
    issues += _extension_mismatch(context, path, rule)
    issues += _invalid_location(context)
    return issues


def _entity_rule_issues(
    schema: Namespace, context: Context, path: str, rule: Mapping[str, Any]
) -> list[Issue]:
    """Too few (required missing) or too many (not allowed) entities."""
    if 'entities' not in rule:
        return []
    file_entities = list(_entities(context))
    rule_entities = [_short(schema, key) for key in rule['entities']]
    issues: list[Issue] = []

    # Required-entity checks do not apply to a file at the dataset root: it is a
    # shared sidecar inherited downward. This mirrors the reference.
    if '/' in context.file.relative_path:
        required = [
            _short(schema, key)
            for key, level in rule['entities'].items()
            if str(level) == 'required'
        ]
        missing = [entity for entity in required if entity not in file_entities]
        if missing:
            issues.append(
                Issue(
                    code='MISSING_REQUIRED_ENTITY',
                    sub_code=', '.join(missing),
                    severity=Severity.ERROR,
                    location=context.file.relative_path,
                    message=f'missing required entities: {", ".join(missing)}',
                    rule=path,
                )
            )

    extra = [entity for entity in file_entities if entity not in rule_entities]
    if extra:
        issues.append(
            Issue(
                code='ENTITY_NOT_IN_RULE',
                sub_code=', '.join(extra),
                severity=Severity.ERROR,
                location=context.file.relative_path,
                message=f'entities not allowed for this file type: {", ".join(extra)}',
                rule=path,
            )
        )
    return issues


def _datatype_mismatch(context: Context, path: str, rule: Mapping[str, Any]) -> list[Issue]:
    """Report a file sitting in a datatype folder its suffix does not belong to."""
    datatype = context.datatype
    if datatype and 'datatypes' in rule and datatype not in list(rule['datatypes']):
        allowed = ', '.join(str(d) for d in rule['datatypes'])
        return [
            Issue(
                code='DATATYPE_MISMATCH',
                severity=Severity.ERROR,
                location=context.file.relative_path,
                message=f"the file is in '{datatype}' but its suffix belongs in: {allowed}",
                rule=path,
            )
        ]
    return []


def _extension_mismatch(context: Context, path: str, rule: Mapping[str, Any]) -> list[Issue]:
    """Report an extension that is not allowed for this suffix."""
    if 'extensions' in rule and context.extension not in list(rule['extensions']):
        allowed = ', '.join(str(e) for e in rule['extensions'])
        return [
            Issue(
                code='EXTENSION_MISMATCH',
                severity=Severity.ERROR,
                location=context.file.relative_path,
                message=f'extension {context.extension!r} is not allowed here; allowed: {allowed}',
                rule=path,
            )
        ]
    return []


def _invalid_location(context: Context) -> list[Issue]:
    """Report a valid name that is in the wrong directory."""
    entities = _entities(context)
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
    return Issue(
        code='INVALID_LOCATION',
        severity=Severity.ERROR,
        location=context.file.relative_path,
        message=f'the file has a valid name but is in the wrong place ({detail})',
    )


def _missing_datatype_directory(
    context: Context, matched: list[tuple[str, Mapping[str, Any]]]
) -> list[Issue]:
    """Report a data file that is not inside a recognised datatype directory.

    This is deliberately STRICTER than the reference TypeScript validator, which
    misses the case: its suffix matching ignores the datatype, and its
    ``DATATYPE_MISMATCH`` check is skipped when the parent directory is not a known
    datatype. The legacy :meth:`BIDSValidator.is_bids` regex does catch it, because
    its patterns cover the whole path, so dropping the check would lose coverage
    this module replaces.

    Metadata files are exempt: the inheritance principle lets a ``.json`` or
    ``.tsv`` sit higher in the tree than the data it describes.
    """
    if context.datatype is not None:
        return []  # the file is in a recognised datatype directory
    if context.extension in INHERITABLE_EXTENSIONS:
        return []  # metadata may be inherited from a higher level
    if not matched or not all('datatypes' in node for _path, node in matched):
        return []  # this file type is not required to live in a datatype directory
    return [
        Issue(
            code='INVALID_LOCATION',
            severity=Severity.ERROR,
            location=context.file.relative_path,
            message=(
                'the file has a valid name but is not in a datatype directory, '
                'expected one of: ' + _allowed_datatypes(matched)
            ),
        )
    ]


def _allowed_datatypes(matched: list[tuple[str, Mapping[str, Any]]]) -> str:
    """List the datatype directories the matched rules allow."""
    allowed: list[str] = []
    for _path, node in matched:
        for datatype in node['datatypes']:
            if str(datatype) not in allowed:
                allowed.append(str(datatype))
    return ', '.join(allowed)


def _reconstruction_failure(schema: Namespace, context: Context) -> list[Issue]:
    """Entities duplicated or out of the schema's canonical order."""
    entities = _entities(context)
    if not entities:
        return []
    ordered = [short for short in _ordered_short(schema) if short in entities]
    parts = [f'{short}-{entities[short]}' for short in ordered]
    expected = '_'.join([*parts, (context.suffix or '') + (context.extension or '')])
    if context.file.name != expected:
        return [
            Issue(
                code='FILENAME_MISMATCH',
                severity=Severity.ERROR,
                location=context.file.relative_path,
                message=f'expected filename: {expected}',
            )
        ]
    return []


# --- helpers --------------------------------------------------------------


def _entities(context: Context) -> dict[str, str]:
    """Real key-label entities from the filename.

    ``FileParts`` records a filename token with no hyphen (the ``dataset`` in
    ``dataset_description.json``) as an entity with a ``None`` value. Those are not
    BIDS entities, so drop them. An empty label (``acq-``) is kept: it is its own
    finding.
    """
    return {key: value for key, value in context.entities.items() if value is not None}


def _entity_by_short(schema: Namespace) -> dict[str, Mapping[str, Any]]:
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
        if long_name in entities:
            name = entities[long_name].get('name')
            if name:
                out.append(str(name))
    _ORDERED_SHORT_MEMO[id(schema)] = out
    return out


def _short(schema: Namespace, long_name: str) -> str:
    entities = schema['objects']['entities']
    if long_name in entities:
        return str(entities[long_name].get('name', long_name))
    return long_name


def _directory_recordings(schema: Namespace) -> set[str]:
    """Extensions of directory-based recordings, e.g. ``.ds``, ``.mefd``.

    The schema marks them with an extension value ending in ``/``.
    """
    cached = _DIR_RECORDING_MEMO.get(id(schema))
    if cached is not None:
        return cached
    out: set[str] = set()
    for definition in schema['objects']['extensions'].values():
        value = str(definition.get('value', ''))
        if value.endswith('/') and value.rstrip('/'):
            out.add(value.rstrip('/'))
    _DIR_RECORDING_MEMO[id(schema)] = out
    return out


def _dataset_type(context: Context) -> str:
    try:
        description = context.dataset.dataset_description
    except (KeyError, OSError, ValueError):
        return 'raw'
    return str(description.get('DatasetType', 'raw'))


def _is_mapping(node: Any) -> bool:
    return isinstance(node, Mapping) or hasattr(node, 'keys')
