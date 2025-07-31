"""Pytest configuration."""

import importlib.resources
import os
from pathlib import Path

import pytest
from bidsschematools.schema import load_schema
from bidsschematools.types import Namespace


@pytest.fixture(scope='session')
def examples() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    ret = os.getenv('BIDS_EXAMPLES')
    if not ret:
        ret = importlib.resources.files(__spec__.parent) / 'data' / 'bids-examples'
        if not any(ret.iterdir()):
            pytest.skip('bids-examples submodule is not checked out')
    else:  # pragma: no cover
        pass
    return Path(ret)


@pytest.fixture(scope='session')
def gitignore_test() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    ret = os.getenv('GITIGNORE_TEST_DIR')
    if not ret:
        ret = importlib.resources.files(__spec__.parent) / 'data' / 'gitignore-test'
        if not any(ret.iterdir()):
            pytest.skip('gitignore-test submodule is not checked out')
    else:  # pragma: no cover
        pass
    return Path(ret)


@pytest.fixture(scope='session')
def schema() -> Namespace:
    """Load BIDS schema for tests."""
    return load_schema()
