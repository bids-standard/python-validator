"""Types for working with file trees."""

from __future__ import annotations

import os
import posixpath
from functools import cached_property
from pathlib import Path

import attrs
from upath import UPath

from . import _typings as t

__all__ = ('FileTree',)


@attrs.define(frozen=True)
class FileTree:
    """Represent a FileTree with cached metadata."""

    path_obj: UPath = attrs.field(repr=False, converter=UPath)
    is_dir: bool = attrs.field(repr=False, default=None)
    parent: FileTree | None = attrs.field(repr=False, default=None, eq=False)
    children: dict[str, FileTree] = attrs.field(repr=False, factory=dict, eq=False)

    def __attrs_post_init__(self) -> None:
        if self.is_dir is None:
            object.__setattr__(self, 'is_dir', self.path_obj.is_dir())
        object.__setattr__(
            self,
            'children',
            {name: attrs.evolve(child, parent=self) for name, child in self.children.items()},
        )

    @classmethod
    def read_from_filesystem(cls, path_obj: str | os.PathLike[str] | UPath) -> t.Self:
        """Read a FileTree from the filesystem."""
        upath_obj = UPath(path_obj)
        children = {}
        if is_dir := upath_obj.is_dir():
            children = {
                entry.name: FileTree.read_from_filesystem(entry) for entry in upath_obj.iterdir()
            }
        return cls(upath_obj, is_dir=is_dir, children=children)

    @property
    def name(self) -> str:
        """The name of the current FileTree node."""
        return self.path_obj.name

    def __contains__(self, relpath: str | os.PathLike[str]) -> bool:
        parts = Path(relpath).parts
        if len(parts) == 0:
            return False
        child = self.children.get(parts[0])
        return bool(child and (len(parts) == 1 or posixpath.join(*parts[1:]) in child))

    def __fspath__(self):
        return self.path_obj.__fspath__()

    def __truediv__(self, relpath: str | os.PathLike) -> FileTree:
        parts = Path(relpath).parts
        child = self
        for part in parts:
            child = child.children[part]
        return child

    @cached_property
    def relative_path(self) -> str:
        """The path of the current FileTree, relative to the root.

        Follows parents up to the root and joins with POSIX separators (/).
        Directories include trailing slashes for simpler matching.
        """
        if self.parent is None:
            return ''

        return posixpath.join(
            self.parent.relative_path,
            f'{self.name}/' if self.is_dir else self.name,
        )
