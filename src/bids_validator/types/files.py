"""Types for working with file trees."""

import os
import posixpath
import stat
from typing import Dict, Self, Union

import attrs


@attrs.define
class DummyDirentry:
    """Partial reimplementation of :class:`os.DirEntry`.

    :class:`os.DirEntry` can't be instantiated, but this can.
    """

    path: str = attrs.field(repr=False, converter=os.fspath)
    name: str = attrs.field(init=False)
    _stat: os.stat_result = attrs.field(init=False, repr=False, default=None)
    _lstat: os.stat_result = attrs.field(init=False, repr=False, default=None)

    def __attrs_post_init__(self) -> None:
        self.name = os.path.basename(self.path)

    def __fspath__(self) -> str:
        return self.path

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        """Return stat_result object for the entry; cached per entry."""
        if follow_symlinks:
            if self._stat is None:
                self._stat = os.stat(self.path, follow_symlinks=True)
            return self._stat
        else:
            if self._lstat is None:
                self._lstat = os.stat(self.path, follow_symlinks=False)
            return self._lstat

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        """Return True if the entry is a directory; cached per entry."""
        _stat = self.stat(follow_symlinks=follow_symlinks)
        return stat.S_ISDIR(_stat.st_mode)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        """Return True if the entry is a file; cached per entry."""
        _stat = self.stat(follow_symlinks=follow_symlinks)
        return stat.S_ISREG(_stat.st_mode)

    def is_symlink(self) -> bool:
        """Return True if the entry is a symlink; cached per entry."""
        _stat = self.stat(follow_symlinks=False)
        return stat.S_ISLNK(_stat.st_mode)


def as_direntry(obj: os.PathLike) -> Union[os.DirEntry, DummyDirentry]:
    """Convert PathLike into DirEntry-like object."""
    if isinstance(obj, os.DirEntry):
        return obj
    return DummyDirentry(obj)


@attrs.define
class FileTree:
    """Represent a FileTree with cached metadata."""

    direntry: Union[os.DirEntry, DummyDirentry] = attrs.field(repr=False, converter=as_direntry)
    parent: Union['FileTree', None] = attrs.field(repr=False, default=None)
    is_dir: bool = attrs.field(default=False)
    children: Dict[str, 'FileTree'] = attrs.field(repr=False, factory=dict)
    name: str = attrs.field(init=False)

    def __attrs_post_init__(self):
        self.name = self.direntry.name
        self.children = {
            name: attrs.evolve(child, parent=self) for name, child in self.children.items()
        }

    @classmethod
    def read_from_filesystem(
        cls,
        direntry: os.PathLike,
        parent: Union['FileTree', None] = None,
    ) -> Self:
        """Read a FileTree from the filesystem.

        Uses :func:`os.scandir` to walk the directory tree.
        """
        self = cls(direntry, parent=parent)
        if self.direntry.is_dir():
            self.is_dir = True
            self.children = {
                entry.name: FileTree.read_from_filesystem(entry, parent=self)
                for entry in os.scandir(self.direntry)
            }
        return self

    def __contains__(self, relpath: os.PathLike):
        parts = posixpath.split(relpath)
        if len(parts) == 0:
            return False
        child = self.children.get(parts[0], False)
        return child and posixpath.join(*parts[1:]) in child

    def __fspath__(self):
        return self.direntry.path
