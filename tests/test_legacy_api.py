import os
from pathlib import Path

import pytest

from bids_validator import BIDSValidator


@pytest.fixture(scope='module')
def validator() -> BIDSValidator:
    return BIDSValidator()


@pytest.mark.parametrize(
    'example',
    [
        'ds001',
        'ds000117',
        'pet001',
        'eeg_matchingpennies',
        'dwi_deriv',
    ],
)
def test_example(validator: BIDSValidator, examples: Path, example: str) -> None:
    ds = examples / example
    for root, _dirs, files in os.walk(ds):
        for file in files:
            fname = str(Path(root).joinpath(file).relative_to(ds).as_posix())
            if fname == '.bidsignore':
                continue
            assert validator.is_bids(f'/{fname}')
