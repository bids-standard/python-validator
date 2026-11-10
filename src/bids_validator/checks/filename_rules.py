"""The schema's filename rules, and which of them describe a file.

The schema's ``rules.files`` lists every legal kind of filename. One rule, as the
schema writes it::

    nonparametric:                      # rules.files.raw.anat.nonparametric
      suffixes: [T1w, T2w, PDw, ...]
      extensions: [.nii.gz, .nii, .json]
      datatypes: [anat]
      entities:
        subject: required
        session: optional
        ...

A file "matches" a rule when its name has one of the rule's suffixes, or when it sits
at the rule's fixed ``path`` (``dataset_description.json``), or when its name fits the
rule's ``stem`` (``participants``). Two kinds of check need to know which rules a file
matches, so the answer is worked out here, for both:

* the filename checks (:mod:`.filenames`) hold the name to those rules: right
  folder, right extension, right entities;
* the rule engine (:mod:`.rules`) shows the file to the schema's other rules
  through :func:`hide_unused_name_parts`.

This follows the reference validator's ``src/validators/filenameIdentify.ts``.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import attrs

from .schema_cache import once_per_schema

# Imported only for type hints; never imported when the program runs, so ``context.py``
# and this module cannot end up importing each other.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

    from ..context import Context

# The names other modules are meant to import from this one.
__all__ = [
    'FilenameRule',
    'all_filename_rules',
    'hide_unused_name_parts',
    'matching_filename_rules',
]


# ``attrs.frozen`` makes a read-only data class from the attributes below.
# ``eq=False`` keeps Python's default comparison by identity: two rules are the same rule
# only if they are the same object, which also lets a rule be put in a ``set``.
@attrs.frozen(eq=False)
class FilenameRule:
    """One ``rules.files`` rule, read out of the schema into plain values.

    A list is ``None`` when the rule does not have it at all, which is not the same
    as an empty list: a rule without ``extensions`` allows any extension.

    Attributes
    ----------
    path : str
        Dotted schema path of the rule, such as ``rules.files.raw.anat.nonparametric``.
    fixed_path : str or None
        The one place a file of this kind may be, for a rule written with ``path``
        (``dataset_description.json``).
    stem : str or None
        A glob the name before its first dot must fit, for a rule written with
        ``stem`` (``participants``, ``*`` for phenotype tables).
    suffixes, extensions, datatypes : tuple of str or None
        What the rule allows.
    entities : tuple of str or None
        The entities the rule allows, as SHORT names (``sub``, ``acq``), the form
        filenames use. The schema lists them by long name (``subject``).
    required_entities : tuple of str
        The entities a file of this kind must have, as short names.

    """

    path: str
    fixed_path: str | None
    stem: str | None
    suffixes: tuple[str, ...] | None
    extensions: tuple[str, ...] | None
    datatypes: tuple[str, ...] | None
    entities: tuple[str, ...] | None
    required_entities: tuple[str, ...]

    @property
    def for_derivatives(self) -> bool:
        """Whether the rule applies only inside a derivative dataset."""
        return self.path.startswith('rules.files.deriv')


def matching_filename_rules(context: Context) -> tuple[FilenameRule, ...]:
    """Return the ``rules.files`` rules that describe this file, best candidates only.

    Every rule the name matches is found first. When several match (``events.tsv`` is
    an events file of many datatypes), the rule for the folder the file is in is
    preferred, then the rules whose entities and extensions fit.

    Parameters
    ----------
    context : Context
        A file, or a directory recording (``sub-01_task-x_meg.ds/``), whose name is
        checked like a file's.

    Returns
    -------
    tuple of FilenameRule
        In schema order. Empty when no rule matches: the file is not part of BIDS.

    """
    return _best(context, _matching(context))


def hide_unused_name_parts(context: Context, rules: tuple[FilenameRule, ...]) -> Context:
    """Return the context as the schema's other rules should see it.

    A part of the name that none of the file's ``rules`` uses is hidden: a file that
    matched no rule at all has no entities, suffix or extension for the rules to read,
    and a ``README`` has no entities. Without this, an unrecognised file such as
    ``.bidsignore`` would be held to the sidecar rules of whatever its name happens to
    resemble. The reference validator calls this ``cleanContext``.

    Parameters
    ----------
    context : Context
        The file.
    rules : tuple of FilenameRule
        What :func:`matching_filename_rules` returned for it.

    Returns
    -------
    Context
        The context itself when nothing is hidden. Otherwise a read-only view of it:
        the hidden parts read as empty, everything else is the context's own, so
        nothing is copied or loaded again.

    """
    hidden: dict[str, Any] = {}
    if not any(rule.entities for rule in rules):
        hidden['entities'] = {}
    if not any(rule.extensions for rule in rules):
        hidden['extension'] = ''
    if not any(rule.suffixes for rule in rules):
        hidden['suffix'] = ''
    if not hidden:
        return context
    # ``cast`` only tells the type checker to treat the view as a Context (it behaves
    # like one); it does nothing when the program runs.
    return cast('Context', _WithHiddenParts(context, hidden))


class _WithHiddenParts:
    """A context with some name parts replaced by empty values."""

    def __init__(self, context: Context, hidden: dict[str, Any]) -> None:
        self._context = context
        self._hidden = hidden

    # Python calls ``__getattr__`` when an attribute is not found on the object itself:
    # ``view.suffix`` comes here, finds ``suffix`` hidden and returns ''; ``view.sidecar``
    # comes here and is passed on to the real context.
    def __getattr__(self, name: str) -> Any:
        if name in self._hidden:
            return self._hidden[name]
        return getattr(self._context, name)


# --- reading the rules out of the schema ----------------------------------


@once_per_schema
def all_filename_rules(schema: Namespace) -> tuple[FilenameRule, ...]:
    """Return every ``rules.files`` rule, in schema order."""
    short = {key: str(entity['name']) for key, entity in schema['objects']['entities'].items()}
    rules: list[FilenameRule] = []
    files = schema['rules'].get('files', {})
    for group in files:
        for path, node in _leaves(files[group], f'rules.files.{group}'):
            entities = node.get('entities')
            rules.append(
                FilenameRule(
                    path=path,
                    fixed_path=_text(node.get('path')),
                    stem=_text(node.get('stem')),
                    suffixes=_texts(node.get('suffixes')),
                    extensions=_texts(node.get('extensions')),
                    datatypes=_texts(node.get('datatypes')),
                    entities=None
                    if entities is None
                    else tuple(short.get(k, k) for k in entities),
                    required_entities=tuple(
                        # A level written as a mapping ({level: ..., enum: ...}) is not
                        # counted as required, as in the reference (``v === 'required'``).
                        short.get(k, k)
                        for k, level in (entities or {}).items()
                        if level == 'required'
                    ),
                )
            )
    return tuple(rules)


def _leaves(node: Any, path: str) -> list[tuple[str, Mapping[str, Any]]]:
    """Return the rules below ``node``: the nodes with a ``path``, ``stem`` or ``suffixes``.

    Anything else is a grouping level (``raw``, ``anat``) to descend into.
    """
    if not isinstance(node, Mapping):
        return []
    keys = node.keys()
    if 'path' in keys or 'stem' in keys or 'suffixes' in keys:
        return [(path, node)]
    return [leaf for key in keys for leaf in _leaves(node[key], f'{path}.{key}')]


def _text(value: Any) -> str | None:
    """Return a schema value as text, keeping ``None`` for "not given"."""
    return None if value is None else str(value)


def _texts(values: Any) -> tuple[str, ...] | None:
    """Return a schema list as a tuple of text, keeping ``None`` for "not given"."""
    return None if values is None else tuple(str(value) for value in values)


@attrs.frozen
class _Index:
    """Where to look first: rule positions by fixed path and by suffix, and stem rules."""

    by_fixed_path: dict[str, tuple[int, ...]]
    by_suffix: dict[str, tuple[int, ...]]
    with_stem: tuple[int, ...]


@once_per_schema
def _index(schema: Namespace) -> _Index:
    """Index :func:`all_filename_rules`, so a file is compared with a few rules, not all."""
    by_fixed_path: dict[str, list[int]] = {}
    by_suffix: dict[str, list[int]] = {}
    with_stem: list[int] = []
    for position, rule in enumerate(all_filename_rules(schema)):
        if rule.fixed_path is not None:
            by_fixed_path.setdefault(rule.fixed_path, []).append(position)
        if rule.stem is not None:
            with_stem.append(position)
        for suffix in rule.suffixes or ():
            by_suffix.setdefault(suffix, []).append(position)
    return _Index(
        by_fixed_path={key: tuple(value) for key, value in by_fixed_path.items()},
        by_suffix={key: tuple(value) for key, value in by_suffix.items()},
        with_stem=tuple(with_stem),
    )


# --- matching -------------------------------------------------------------


def _matching(context: Context) -> list[FilenameRule]:
    """Return every rule the file's name matches, in schema order.

    A rule matches by its fixed path, by its stem glob, or by suffix. Matching by
    suffix ignores the folder, as in the reference, which is why a file in the wrong
    folder still finds its rule (and is then reported as in the wrong folder).
    Derivative rules only apply inside a derivative dataset.
    """
    schema = context.schema
    rules = all_filename_rules(schema)
    index = _index(schema)
    positions = {
        *index.by_fixed_path.get(context.path[1:], ()),  # path starts with '/'
        *index.by_suffix.get(context.suffix or '', ()),
        *(position for position in index.with_stem if _fits_stem(rules[position], context)),
    }
    derivative = context.dataset.dataset_description.get('DatasetType') == 'derivative'
    return [
        rules[position]
        for position in sorted(positions)
        if derivative or not rules[position].for_derivatives
    ]


def _fits_stem(rule: FilenameRule, context: Context) -> bool:
    """Whether the name before its first dot fits the rule's glob, in the rule's folder."""
    stem = context.file.name.split('.')[0]
    if not fnmatch.fnmatchcase(stem, str(rule.stem)):
        return False
    return rule.datatypes is None or context.datatype in rule.datatypes


def _best(context: Context, rules: list[FilenameRule]) -> tuple[FilenameRule, ...]:
    """Keep the best candidates: the rules for the file's folder, then those that fit."""
    if len(rules) > 1:
        in_folder = [
            r for r in rules if r.datatypes is not None and context.datatype in r.datatypes
        ]
        rules = in_folder or rules
    if len(rules) > 1:
        fitting = [r for r in rules if _fits(r, context)]
        rules = fitting or rules
    return tuple(rules)


def _fits(rule: FilenameRule, context: Context) -> bool:
    """Whether the rule allows the file's extension and every entity in its name."""
    if rule.extensions is not None and context.extension not in rule.extensions:
        return False
    return rule.entities is None or set(context.entities) <= set(rule.entities)
