"""Pytest configuration."""

import os
from pathlib import Path

import pytest
from bidsschematools.schema import load_schema
from bidsschematools.types.namespace import Namespace

from .data import load_data


def get_submod_or_env(dir_name: str, env_var: str) -> Path:
    """Get submodule data path or override from environment variable.

    Signals to skip tests if submodule is not checked out and no variable is set.
    """
    ret = os.getenv(env_var)
    if not ret:
        data_path = load_data(dir_name)
        if not any(data_path.iterdir()):
            pytest.skip(f'{dir_name} submodule is not checked out')
        return data_path
    return Path(ret)


@pytest.fixture(scope='session')
def examples() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    return get_submod_or_env('bids-examples', 'BIDS_EXAMPLES')


@pytest.fixture(scope='session')
def gitignore_test() -> Path:
    """Get bids-examples from submodule, allow environment variable override."""
    return get_submod_or_env('gitignore-test', 'GITIGNORE_TEST_DIR')


@pytest.fixture(scope='session')
def mrs_data() -> Path:
    """Get MRS data from submodule, allow environment variable override."""
    mrs_nifti_standard = get_submod_or_env('mrs_nifti_standard', 'MRS_NIFTI_STANDARD')
    return mrs_nifti_standard / 'example_data' / 'examples'


@pytest.fixture(scope='session')
def schema() -> Namespace:
    """Load BIDS schema for tests."""
    return load_schema()
