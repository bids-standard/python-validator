"""Test bids_validator.bidsignore."""

from pathlib import Path

import pytest

from bids_validator.bidsignore import Ignore, compile_pat, filter_file_tree
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
        # *o matches things with basename ending in o, including parent directories
        ('*o', ['foo', 'foo/', 'bar/foo', 'bar/foo/', 'foo/bar'], ['bar', 'bar/baz', 'bar/bar/']),
        # Leading **/ matches in all directories
        (
            '**/foo',
            ['foo', 'foo/', 'bar/foo', 'bar/foo/', 'foo/bar'],
            ['foobar/baz', 'foobar/baz/', 'baz/foobar', 'baz/barfoo'],
        ),
        ('**/foo/bar', ['foo/bar', 'foo/bar/', 'a/foo/bar'], ['foo/', 'bar/foo', 'bar']),
        # Trailing /** matches everything inside a root-relative directory
        ('foo/**', ['foo/', 'foo/x', 'foo/x/y/z'], ['foo', 'bar/foo/x/y/z']),
        # /**/ matches zero or more directories
        ('a/**/b', ['a/b', 'a/x/b', 'a/x/y/b'], ['x/a/b', 'x/a/y/b']),
        # ** surrounded by something other than slashes acts like a regular *
        ('a/x**/b', ['a/x/b', 'a/xy/b'], ['x/a/b', 'x/a/y/b', 'a/x/y/b']),
        # Escaped special prefixes
        (r'\#*', ['#', '#foo'], ['foo', 'bar#']),
        (r'\!*', ['!', '!foo'], ['foo', 'bar!']),
    ],
)
def test_patterns(pattern, hits, misses):
    """Test expected hits and misses of ignore patterns."""
    regex = compile_pat(pattern)
    for fname in hits:
        assert regex.match(fname), f'"{fname}" should match "{pattern}"'
    for fname in misses:
        assert not regex.match(fname), f'"{fname}" should not match "{pattern}"'


def test_skipped_patterns():
    """Test ignore patterns that should match nothing."""
    assert compile_pat('') is None
    assert compile_pat('# commented line') is None
    assert compile_pat('     ') is None
    with pytest.raises(ValueError, match='Inverted patterns not supported'):
        compile_pat('!inverted pattern')


def test_Ignore_ds000117(examples):
    """Test that we can load a .bidsignore file and match a file."""
    ds000117 = FileTree.read_from_filesystem(examples / 'ds000117')
    ignore = Ignore.from_file(ds000117.children['.bidsignore'])
    assert 'run-*_echo-*_FLASH.json' in ignore.patterns
    assert 'sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz' in ds000117
    assert ignore.match('sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz')
    assert not ignore.match('acq-mprage_T1w.json')
    flash_file = (
        ds000117.children['sub-01']
        .children['ses-mri']
        .children['anat']
        .children['sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz']
    )
    assert ignore.match(flash_file.relative_path)


def test_filter_file_tree(examples):
    """Test file tree filtering with .bidsignore."""
    ds000117 = FileTree.read_from_filesystem(examples / 'ds000117')
    assert '.bidsignore' in ds000117
    assert 'sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz' in ds000117

    filtered = filter_file_tree(ds000117)
    assert '.bidsignore' not in filtered
    assert 'sub-01/ses-mri/anat/sub-01_ses-mri_run-1_echo-1_FLASH.nii.gz' not in filtered

    ds000247 = FileTree.read_from_filesystem(examples / 'ds000247')
    assert '.bidsignore' not in ds000247

    filtered = filter_file_tree(ds000247)
    assert filtered is ds000247


def _walk(tree: FileTree):
    for child in tree.children.values():
        if child.is_dir:
            yield from _walk(child)
        else:
            yield child


def test_gitignore_battery(gitignore_test):
    """Test our implementation against a gitignore battery."""
    filetree = FileTree.read_from_filesystem(gitignore_test)
    ignore = Ignore.from_file(filetree.children['.gitignore'])
    # Remove inverted patterns
    ignore.patterns = [patt for patt in ignore.patterns if not patt.startswith('!')]

    expected_failures = Ignore(
        [
            '.git*',  # Ignore .git/, .gitignore, etc
            'README.md',  # README is an exception
            # Inverted patterns are not supported
            'foo*.html',
            '/log/foo.log',
            'findthis*',
            # Nested gitignore swaps expectations for all files
            'git-sample-3/',
            # Inversions in nested gitignores
            'arch/foo/kernel/vmlinux*',
            'htmldoc/*.html',
        ]
    )

    for file in _walk(filetree):
        if expected_failures.match(file.relative_path):
            continue
        if ignore.match(file.relative_path):
            assert Path(file).read_text().strip() == 'foo: FAIL', (
                f'{file.relative_path} should have failed'
            )
        else:
            assert Path(file).read_text().strip() == 'foo: OK', (
                f'{file.relative_path} should have passed'
            )
