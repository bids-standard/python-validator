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
        ret = importlib.resources.files(__package__) / 'data' / 'bids-examples'
        if not ret.exists():
            pytest.skip('Missing examples')
    return Path(ret)
