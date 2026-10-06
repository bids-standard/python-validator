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

from bidsschematools.types.context import Subject
from bidsschematools.types.namespace import Namespace

from .bidsignore import Ignore, IgnoreMany
from .context import Context, Dataset, Sessions
from .issues import DatasetIssues, Issue, Severity

if TYPE_CHECKING:
    from .bidsignore import HasMatch
    from .types.files import FileTree

__all__ = [
    'DEFAULT_IGNORES',
    'DERIVATIVES_DIR',
    'FILENAME_ISSUES',
    'collect_filename_issues',
    'filename_issues',
    'iter_contexts',
]

# Paths the reference validator never name-checks, from its ``src/files/ignore.ts``.
# ``.*`` covers dotfiles such as ``.DS_Store`` and ``.bidsignore`` itself; the named
# directories hold files BIDS does not constrain.
DEFAULT_IGNORES = ('.git**', '.*', 'sourcedata/', 'code/', 'stimuli/', 'log/')

# A derivative is a separate dataset that happens to live inside another one, and its
# files follow ``rules.files.deriv`` rather than the raw rules of the dataset around
# them. Checking a derivative against its parent's rules reports errors for perfectly
# legal files, so the walk stops at this boundary. The reference validator does the same
# thing twice over: it drops ``derivatives`` from the tree ("Remove derivatives from the
# main fileTree", ``src/validators/bids.ts``) and then skips any remaining context whose
# path contains it while the root dataset is raw.
#
# To check a derivative, point :func:`collect_filename_issues` at the derivative's own
# root. Its ``dataset_description.json`` declares ``DatasetType: derivative``, and the
# derivative filename rules are then the ones that apply.
DERIVATIVES_DIR = 'derivatives'

# Extensions the BIDS inheritance principle allows to sit higher in the tree than the
# data they describe, so they are exempt from the datatype-directory requirement.
INHERITABLE_EXTENSIONS = frozenset({'.json', '.tsv'})

# The filename/path codes this module can emit. Every one is an error; the reference
# defines no filename warnings.
#
# NOT_INCLUDED is the one code the BIDS schema itself defines, at rules.errors, so it is
# read from there at runtime by _schema_error rather than repeated here. The other nine
# appear nowhere in the schema (verified against every leaf of schema.json); they come
# from the reference validator's catalog in src/issues/list.ts, and are mirrored here so
# the provenance is explicit and the output stays interchangeable.
FILENAME_ISSUES: dict[str, str] = {
    'NOT_INCLUDED': '(defined by the schema at rules.errors.NotIncluded)',
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
#
# Four entry points, from coarsest to finest:
#
#   collect_filename_issues(tree, schema) -> DatasetIssues
#       Validate a whole dataset. This is what most callers want.
#   iter_contexts(dataset)                -> Iterator[Context]
#       Walk the dataset, yielding the files worth checking.
#   build_ignore(tree)                    -> IgnoreMany
#       The ignore matcher those two use.
#   filename_issues(context)              -> list[Issue]
#       Check a single file. The unit a future rule engine would call.
#
# Only the first is needed to validate a dataset; the rest are exposed so callers
# can reuse the walk, the ignore rules, or the per-file check on their own.


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
    # Dataset pairs the file tree with the schema and caches dataset_description.json,
    # which the checks need to know whether derivative rules apply.
    dataset = Dataset(tree, schema)
    issues = DatasetIssues()
    # One file at a time: build its facts, check them, add whatever came back.
    for context in iter_contexts(dataset):
        issues.extend(filename_issues(context))
    return issues


def iter_contexts(dataset: Dataset, ignore: HasMatch | None = None) -> Iterator[Context]:
    """Yield a :class:`~bids_validator.context.Context` for every validatable file.

    Skips anything the dataset's ``.bidsignore`` or :data:`DEFAULT_IGNORES` match.
    Directory recordings (CTF ``.ds``, MEF ``.mefd``, OME-Zarr ...) are single units:
    the recording itself is yielded so its own name is validated, but the walk does not
    descend, so its vendor-named internals are never name-checked.
    """
    if ignore is None:
        ignore = build_ignore(dataset.tree)
    recordings = _directory_recordings(dataset.schema)
    yield from _walk(dataset.tree, dataset, recordings, ignore)


def build_ignore(tree: FileTree) -> IgnoreMany:
    """Build the ignore matcher: the reference defaults plus the dataset's .bidsignore.

    Both halves matter. Without :data:`DEFAULT_IGNORES` every ``.DS_Store`` and hidden
    file would be reported, which the reference validator never does; without the
    dataset's own ``.bidsignore`` the user cannot exempt their own extra files.
    """
    ignores = [Ignore(list(DEFAULT_IGNORES))]
    bidsignore = tree.children.get('.bidsignore')
    if bidsignore is not None:
        ignores.append(Ignore.from_file(bidsignore))
    return IgnoreMany(ignores)


def filename_issues(context: Context) -> list[Issue]:
    """Return every filename/path finding for one file.

    The heart of the module. Three steps:

    1. Find which ``rules.files`` rule or rules the file matches. None means the file
       is not BIDS at all, reported as ``NOT_INCLUDED``.
    2. Narrow several matches down to the best candidate.
    3. Run each check family, concatenating the findings.

    Works for a directory recording too. ``FileParts`` gives a directory a trailing
    slash in its extension (``.ds/``), which is exactly how the schema spells those
    extensions, so the ordinary rules apply to the folder's name.

    ``context`` carries everything known about the one file: its path, the entities,
    suffix and extension parsed from its name, the datatype folder it sits in, and a
    link back to the dataset and schema. Nothing here opens the file.
    """
    schema = context.schema
    relpath = context.file.relative_path

    matched = _find_rule_matches(schema, context)
    if not matched:
        # The schema defines this one, so take its code, level and wording from there.
        code, severity, message = _schema_error(schema, 'NotIncluded')
        return [
            Issue(
                code=code,
                severity=severity,
                location=relpath,
                message=message or f'{context.file.name} does not match any BIDS naming rule',
            )
        ]

    # Several rules can match one name; keep the best candidate(s).
    matched = _narrow(schema, context, matched)

    # Each check returns a list, so the findings simply add up. The code each one can
    # emit is named alongside it.
    issues: list[Issue] = []
    issues += _missing_label(context, matched)  # ENTITY_WITH_NO_LABEL
    issues += _entity_label_check(schema, context)  # INVALID_ENTITY_LABEL
    issues += _check_rules(schema, context, matched)  # MISSING_REQUIRED_ENTITY,
    # ENTITY_NOT_IN_RULE, DATATYPE_MISMATCH, EXTENSION_MISMATCH, INVALID_LOCATION,
    # ALL_FILENAME_RULES_HAVE_ISSUES
    issues += _missing_datatype_directory(context, matched)  # INVALID_LOCATION
    issues += _reconstruction_failure(schema, context)  # FILENAME_MISMATCH
    return issues


# --- walking --------------------------------------------------------------


def _walk(
    tree: FileTree,
    dataset: Dataset,
    recordings: set[str],
    ignore: HasMatch,
    subject: Subject | None = None,
) -> Iterator[Context]:
    """Yield one Context per file, depth first, skipping ignored paths.

    A directory whose name ends in a directory-recording extension (CTF ``.ds``, MEF
    ``.mefd``, OME-Zarr) is one recording, not a folder of files. It is yielded so its
    own name is validated, but the walk does not descend, so its vendor-named internals
    are never name-checked.

    A :data:`DERIVATIVES_DIR` directory is a dataset boundary and is not descended into
    at all, since the rules on the far side of it are different ones.

    Each context carries the :class:`Subject` of the enclosing ``sub-*`` directory, so
    later content checks have it without a second walk.
    """
    # Entering a sub-* directory establishes the subject every file below it belongs to.
    if subject is None and tree.name.startswith('sub-'):
        subject = Subject(Sessions(tree))

    for child in tree.children.values():
        if ignore.match(child.relative_path):
            continue
        if child.is_dir:
            if child.name == DERIVATIVES_DIR:
                # A separate dataset with separate rules. See DERIVATIVES_DIR.
                continue
            if any(child.name.endswith(ext) for ext in recordings):
                # A directory recording is one unit: its NAME is checked like a file's,
                # but its vendor-named internals are not, so yield it without descending.
                yield Context(child, dataset, subject)
                continue
            yield from _walk(child, dataset, recordings, ignore, subject)
        else:
            yield Context(child, dataset, subject)


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
    """Collect leaf rules under ``node`` into ``out`` as ``(dotted_path, rule)`` pairs.

    A node is a leaf when it carries ``path``, ``stem`` or ``suffixes``. Anything else is
    a grouping level to descend into.
    """
    if not _is_mapping(node):
        return
    if 'path' in node or 'stem' in node or 'suffixes' in node:
        out.append((path, node))
        return
    for key in node:
        _collect(node[key], f'{path}.{key}', out)


def _find_rule_matches(schema: Namespace, context: Context) -> list[tuple[str, Mapping[str, Any]]]:
    """Return every ``rules.files`` rule the file matches.

    Several rules can match one name; :func:`_narrow` picks between them. An empty
    result means the file is not BIDS at all, reported as ``NOT_INCLUDED``.
    """
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
    """Return whether one rule applies, by exact path, stem glob, or suffix.

    Suffix matching deliberately ignores the datatype, mirroring the TypeScript
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
    """Return whether the extension is allowed and the entities fit within the rule.

    The second tie-breaker in :func:`_narrow`, used when the datatype did not settle it.
    """
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
    """Check the file against the matched rule or rules and return the findings.

    With one candidate, report its problems directly. With several, accept the file if
    any candidate is satisfied cleanly; only when every candidate has a problem is
    ``ALL_FILENAME_RULES_HAVE_ISSUES`` reported.
    """
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
    """Run the four rule-scoped checks for one candidate rule.

    Entities, datatype directory, extension, and placement within the subject or
    session hierarchy.
    """
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
    return Issue(
        code='INVALID_LOCATION',
        severity=Severity.ERROR,
        location=context.file.relative_path,
        message=f'the file has a valid name but is in the wrong place ({detail})',
    )


def _at_inheritance_level(relpath: str) -> bool:
    """Report whether the file sits at a level the inheritance principle allows.

    The principle lets a sidecar sit ABOVE the data it describes: at the dataset
    root, beside a subject, or beside a session. Those are the three places, and
    in each the file sits DIRECTLY in that folder.

    A ``.json`` inside ``sub-01/ses-pre/awwww/`` inherits nothing. It is in a
    folder BIDS does not read, exactly as lost as the image beside it, so
    exempting it for its extension reported only half of what was wrong.
    """
    parts = [p for p in relpath.strip('/').split('/') if p]
    depth = 0
    if depth < len(parts) and parts[depth].startswith('sub-'):
        depth += 1
        if depth < len(parts) and parts[depth].startswith('ses-'):
            depth += 1
    # What remains should be the filename alone; more means the file sits inside
    # a container directory, and that container is not a datatype.
    return len(parts) - depth <= 1


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
    if context.extension in INHERITABLE_EXTENSIONS and _at_inheritance_level(
        context.file.relative_path
    ):
        return []  # metadata legitimately sitting above the data it describes
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
    # A directory recording's extension carries a trailing slash (``.ds/``) because that
    # is how the schema spells it, but the folder on disk is named without one. Drop it
    # so the rebuilt name is comparable, and readable in the message.
    extension = (context.extension or '').rstrip('/')
    expected = '_'.join([*parts, (context.suffix or '') + extension])
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
        if long_name in entities:
            name = entities[long_name].get('name')
            if name:
                out.append(str(name))
    _ORDERED_SHORT_MEMO[id(schema)] = out
    return out


def _short(schema: Namespace, long_name: str) -> str:
    """Convert an entity's long schema name to the short form used in filenames."""
    entities = schema['objects']['entities']
    if long_name in entities:
        return str(entities[long_name].get('name', long_name))
    return long_name


def _schema_error(schema: Namespace, name: str) -> tuple[str, Severity, str | None]:
    """Read a schema-defined error from ``rules.errors``, as (code, severity, message).

    A handful of structural errors are defined by the schema itself, so their code,
    level and wording belong to it rather than to us. Falls back to the entry's own name
    and ``error`` if the schema does not define it, which keeps an older schema working.
    """
    entry = schema['rules'].get('errors', {}).get(name, {})
    code = str(entry.get('code', name))
    level = str(entry.get('level', 'error'))
    severity = Severity.WARNING if level == 'warning' else Severity.ERROR
    message = entry.get('message')
    # Schema messages are multi-line YAML blocks; a finding's message is one line.
    return code, severity, ' '.join(str(message).split()) if message else None


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
    """Return the dataset's ``DatasetType``, defaulting to ``raw``.

    Decides whether derivative-only filename rules apply. A missing or unreadable
    ``dataset_description.json`` degrades to ``raw`` rather than aborting the run.
    """
    try:
        description = context.dataset.dataset_description
    except (KeyError, OSError, ValueError):
        return 'raw'
    return str(description.get('DatasetType', 'raw'))


def _is_mapping(node: Any) -> bool:
    """Return whether ``node`` behaves like a mapping.

    ``Namespace`` is dict-like but is not always a ``Mapping`` instance, so both are
    accepted.
    """
    return isinstance(node, Mapping) or hasattr(node, 'keys')
