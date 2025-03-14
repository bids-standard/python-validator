"""Pytest configuration."""

import importlib.resources
import os
from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def examples() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    ret = os.getenv('BIDS_EXAMPLES')
    if not ret:
        ret = importlib.resources.files() / 'data' / 'bids-examples'
        if not any(ret.iterdir()):
            pytest.skip('bids-examples submodule is not checked out')
    return Path(ret)
