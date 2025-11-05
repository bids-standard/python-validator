"""Pytest configuration."""

import os
from pathlib import Path

import pytest
from acres import typ as at
from bidsschematools.schema import load_schema
from bidsschematools.types import Namespace

from .data import load_data


@pytest.fixture(scope='session')
def examples() -> at.Traversable:
    """Get bids-examples from submodule, allow environment variable override."""
    ret = os.getenv('BIDS_EXAMPLES')
    if not ret:
        examples = load_data('bids-examples')
        if not any(examples.iterdir()):
            pytest.skip('bids-examples submodule is not checked out')
        return examples
    return Path(ret)


@pytest.fixture(scope='session')
def gitignore_test() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    ret = os.getenv('GITIGNORE_TEST_DIR')
    if not ret:
        test_data = load_data('gitignore-test')
        if not any(test_data.iterdir()):
            pytest.skip('gitignore-test submodule is not checked out')
        return test_data
    return Path(ret)


@pytest.fixture(scope='session')
def schema() -> Namespace:
    """Load BIDS schema for tests."""
    return load_schema()
