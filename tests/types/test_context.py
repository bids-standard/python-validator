from bids_validator.types import context


def test_imports():
    """Verify that we do not declare attributes that are not generated."""
    for name in context.__all__:
        assert hasattr(context, name), f'Failed to import {name} from context'
