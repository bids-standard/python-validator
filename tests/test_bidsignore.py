"""Test bids_validator.bidsignore."""

import pytest

from bids_validator.bidsignore import Ignore, compile_pat
from bids_validator.types.files import FileTree


@pytest.mark.parametrize(
    ('pattern', 'hits', 'misses'),
    [
        ('/', ['/'], ['dir/', 'file']),
        # Match file or directory named foo
        ('foo', ['foo', 'foo/', 'bar/foo', 'bar/foo/'], ['bar', 'foobar', 'barfoo', 'barfoo/']),
        # Directories named foo only
        ('foo/', ['foo/', 'bar/foo/'], ['foo', 'bar/foo', 'bar', 'foobar', 'barfoo', 'barfoo/']),
        # Files or directories at the root
        ('/foo', ['foo', 'foo/'], ['bar/foo', 'bar/foo/', 'bar', 'foobar', 'barfoo', 'barfoo/']),
        # doc/frotz/ examples from GITIGNORE(5)
        ('doc/frotz/', ['doc/frotz/'], ['a/doc/frotz/']),
        ('frotz/', ['frotz/', 'doc/frotz/', 'a/doc/frotz/'], []),
        # * matches everything because everything has a basename
        ('*', ['foo', 'foo/', 'foo/bar', 'foo/bar/'], []),
        # *o matches things with basename ending in o
        ('*o', ['foo', 'foo/', 'bar/foo', 'bar/foo/'], ['foo/bar', 'foo/bar/']),
        # Leading **/ matches in all directories
        ('**/foo', ['foo', 'foo/', 'bar/foo', 'bar/foo/'], ['foo/bar', 'foo/bar/', 'baz/foobar']),
        ('**/foo/bar', ['foo/bar', 'foo/bar/', 'a/foo/bar'], ['foo/', 'bar/foo', 'bar']),
        # Trailing /** matches everything inside a root-relative directory
        ('foo/**', ['foo/', 'foo/x', 'foo/x/y/z'], ['foo', 'bar/foo/x/y/z']),
        # /**/ matches zero or more directories
        ('a/**/b', ['a/b', 'a/x/b', 'a/x/y/b'], ['x/a/b', 'x/a/y/b']),
        # ** surrounded by something other than slashes acts like a regular *
        ('a/x**/b', ['a/x/b', 'a/xy/b'], ['x/a/b', 'x/a/y/b', 'a/x/y/b']),
    ],
)
def test_patterns(pattern, hits, misses):
    """Test expected hits and misses of ignore patterns."""
    regex = compile_pat(pattern)
    for fname in hits:
        assert regex.match(fname)
    for fname in misses:
        assert not regex.match(fname)


def test_skipped_patterns():
    """Test ignore patterns that should match nothing."""
    assert compile_pat('') is None
    assert compile_pat('# commented line') is None
    assert compile_pat('     ') is None


def test_Ignore_ds000117(examples):
    """Test that we can load a .bidsignore file and match a file."""
    ds000117 = FileTree.read_from_filesystem(examples / 'ds000117')
    ignore = Ignore.from_file(ds000117.children['.bidsignore'])
    assert 'run-*_echo-*_FLASH.json' in ignore.patterns
    assert 'sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz' in ds000117
    assert ignore.match('sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz')
    flash_file = (
        ds000117.children['sub-01']
        .children['ses-mri']
        .children['anat']
        .children['sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz']
    )
    assert ignore.match(flash_file.relative_path)
