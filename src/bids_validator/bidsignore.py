"""Utilities for working with .bidsignore files."""

import os
import re
from functools import lru_cache
from typing import Self, Union

import attrs

from .types.files import FileTree


@lru_cache
def compile_pat(pattern: str) -> Union[re.Pattern, None]:
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

    prefix = '^' if relative_match else '^(.*/|)'
    postfix = r'/\Z' if directory_match else r'/?\Z'

    # "**/" matches zero or more directories, so the separating slash needs to be optional
    out_pattern = '/'.join(parts).replace('.*/', '.*/?')
    out_pattern = f'{prefix}{out_pattern}{postfix}'

    if invert:
        raise ValueError(f'Inverted patterns not supported: {orig}')
        # out_pattern = f'(?!{out_pattern})'

    return re.compile(out_pattern)


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
        if any(compile_pat(pattern).match(relpath) for pattern in self.patterns):
            self.history.append(relpath)
            return True
        return False

    def __add__(self, other) -> Self:
        return self.__class__(patterns=self.patterns + other.patterns)


def filter_file_tree(filetree: FileTree) -> FileTree:
    """Stub."""
    bidsignore = filetree.children.get('.bidsignore')
    if not bidsignore:
        return filetree
    ignore = Ignore.from_file(bidsignore) + Ignore(['/.bidsignore'])
    return _filter(filetree, ignore)


def _filter(filetree: FileTree, ignore: Ignore) -> FileTree:
    items = filetree.children.items()
    children = {
        name: _filter(child, ignore)
        for name, child in items
        if not ignore.match(child.relative_path)
    }

    if any(children.get(name) is not child for name, child in items):
        filetree = attrs.evolve(filetree, children=children)

    return filetree
