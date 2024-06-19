"""Test bids_validator.bidsignore."""

import pytest

from bids_validator.bidsignore import compile_pat


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
