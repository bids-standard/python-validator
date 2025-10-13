"""Utilities for working with .bidsignore files."""

import os
import re
from functools import lru_cache
from typing import Protocol

import attrs

from .types.files import FileTree


@lru_cache
def compile_pat(pattern: str) -> re.Pattern | None:
    """Compile .gitignore-style ignore lines to regular expressions."""
    orig = pattern
    # A line starting with # serves as a comment.
    if pattern.startswith('#'):
        return None

    # An optional prefix "!" which negates the pattern;
    invert = pattern.startswith('!')

    # Put a backslash ("\") in front of the first hash for patterns that begin with a hash.
    # Put a backslash ("\") in front of the first "!" for patterns that begin with a literal "!"
    if pattern.startswith((r'\#', r'\!')):
        pattern = pattern[1:]  # Unescape

    # Trailing spaces are ignored unless they are quoted with backslash ("\").
    pattern = re.sub(r'(?<!\\) +$', '', pattern)

    # A blank line matches no files, so it can serve as a separator for readability.
    if pattern == '':
        return None

    # If there is a separator at the beginning or middle (or both) of the pattern,
    # then the pattern is relative to the [root]
    relative_match = pattern == '/' or '/' in pattern[:-1]
    # If there is a separator at the end of the pattern then the pattern will only match
    # directories, otherwise the pattern can match both files and directories.
    directory_match = pattern.endswith('/')

    # This does not handle character ranges correctly except when they are also valid regex
    parts = [
        '.*'
        if part == '**'
        else part.replace('*', '[^/]*').replace('?', '[^/]').replace('.', r'\.')
        for part in pattern.strip('/').split('/')
    ]

    prefix = '^' if relative_match else '^(?:.*/|)'
    postfix = r'/' if directory_match else r'(/|\Z)'

    # "**/" matches zero or more directories, so wrap in an optional segment
    out_pattern = '/'.join(parts).replace('.*/', '(?:.*/)?')
    out_pattern = f'{prefix}{out_pattern}{postfix}'

    if invert:
        raise ValueError(f'Inverted patterns not supported: {orig}')
        # out_pattern = f'(?!{out_pattern})'

    return re.compile(out_pattern)


class HasMatch(Protocol):  # noqa: D101
    def match(self, relpath: str) -> bool: ...  # noqa: D102


@attrs.define
class Ignore:
    """Collection of .gitignore-style patterns.

    Tracks successfully matched files for reporting.
    """

    patterns: list[str] = attrs.field(factory=list)
    history: list[str] = attrs.field(factory=list, init=False)

    @classmethod
    def from_file(cls, pathlike: os.PathLike):
        """Load Ignore contents from file."""
        with open(pathlike) as fobj:
            return cls([line.rstrip('\n') for line in fobj])

    def match(self, relpath: str) -> bool:
        """Match a relative path against a collection of ignore patterns."""
        if any(compile_pat(pattern).match(relpath) for pattern in self.patterns if pattern):
            self.history.append(relpath)
            return True
        return False


@attrs.define
class IgnoreMany:
    """Match against several ignore filters."""

    ignores: list[Ignore] = attrs.field()

    def match(self, relpath: str) -> bool:
        """Return true if any filters match the given file.

        Will short-circuit, so ordering is significant for side-effects,
        such as recording files ignored by a particular filter.
        """
        return any(ignore.match(relpath) for ignore in self.ignores)


def filter_file_tree(filetree: FileTree) -> FileTree:
    """Read .bidsignore and filter file tree."""
    bidsignore = filetree.children.get('.bidsignore')
    if not bidsignore:
        return filetree
    ignore = IgnoreMany([Ignore.from_file(bidsignore), Ignore(['/.bidsignore'])])
    return _filter(filetree, ignore)


def _filter(filetree: FileTree, ignore: HasMatch) -> FileTree:
    items = filetree.children.items()
    children = {
        name: _filter(child, ignore)
        for name, child in items
        if not ignore.match(child.relative_path)
    }

    # XXX This check may not be worth the time. Profile this.
    if any(children.get(name) is not child for name, child in items):
        filetree = attrs.evolve(filetree, children=children)

    return filetree
