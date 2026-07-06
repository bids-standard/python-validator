import json

import fsspec
import pytest

from collections.abc import Generator

from bidsschematools.schema import load_schema

from bids_validator import context
from bids_validator.expression_language import interpret

from bids_validator.types.files import FileTree


@pytest.fixture
def memfs() -> Generator[fsspec.AbstractFileSystem, None, None]:
    mem = fsspec.filesystem('memory')
    mem.store.clear()
    yield mem
    mem.store.clear()

@pytest.mark.parametrize(
    ("test"),
    load_schema().meta.expression_tests
)
def test_interpret(memfs, tmp_path, schema, test):
    memfs.pipe(
        {
            '/dataset_description.json': json.dumps(
                {'Name': 'MRS Test Dataset', 'BIDSVersion': '1.10.1'}
            ).encode(),
        }
    )
    memfs.get('memory:///', str(tmp_path), recursive=True)
    dataset = FileTree.read_from_filesystem(tmp_path)

    file = dataset / 'dataset_description.json'

    ds = context.Dataset(dataset, schema)

    file_context = context.Context(file, ds, None)

    expr = test['expression']
    expected = test['result']

    result = interpret(expr, file_context)

    assert result == expected






