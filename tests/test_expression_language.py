import json
import math
import typing as ty
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace

import fsspec
import numpy as np
import pytest
from bidsschematools.schema import load_schema
from bidsschematools.types.namespace import Namespace

from bids_validator import context
from bids_validator.expression_language import el_namespace, evaluate, interpret, parse, truthy
from bids_validator.types.files import FileTree


class ExpressionTest(ty.TypedDict):
    expression: str
    result: ty.Any


@pytest.fixture
def memfs() -> Generator[fsspec.AbstractFileSystem, None, None]:
    mem = fsspec.filesystem('memory')
    mem.store.clear()
    yield mem
    mem.store.clear()


@pytest.mark.parametrize(('test'), load_schema().meta.expression_tests)
def test_interpret(
    memfs: fsspec.AbstractFileSystem,
    tmp_path: Path,
    schema: Namespace,
    test: ExpressionTest,
) -> None:
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


# --- Behaviour beyond ``schema.meta.expression_tests`` ----------------------
#
# The schema's own vectors (above) never compare numbers, never read a value from a
# real file, and never test truthiness of arrays. The schema's rules do all three: 30
# of 129 ``rules.checks`` use < <= > >= or **, and 29 are gated on
# ``type(<something>) != "null"``. Each vector below pins one of those behaviours to
# the schema's documentation (bids-specification ``src/schema/README.md``, section
# "Expressions") or, where it is silent, to the reference implementation.

EXTRA_VECTORS = [
    # Ordering operators. Two strings compare as text, anything else as numbers.
    pytest.param('1 < 2', True, id='less-than'),
    pytest.param('2 <= 2', True, id='less-or-equal'),
    pytest.param('3 > 2', True, id='greater-than'),
    pytest.param('2 >= 3', False, id='greater-or-equal'),
    pytest.param('"a" < "b"', True, id='strings-compare-as-text'),
    pytest.param('"10" < "9"', True, id='numeric-strings-still-compare-as-text'),
    pytest.param('"10" > 9', True, id='string-and-number-compare-as-numbers'),
    pytest.param('"n/a" > 0', False, id='not-a-number-compares-false'),
    # README: "null == 1 -> false. Also <, >, <= and >=".
    pytest.param('null < 1', False, id='null-less-than-is-false'),
    pytest.param('null >= 0', False, id='null-greater-or-equal-is-false'),
    # Arithmetic. README: null + 1, null - 1, null * 1, null / 1 are all null.
    pytest.param('10 ** 2', 100, id='power'),
    pytest.param('10 ** -3', 0.001, id='power-negative'),
    pytest.param('null + 1', None, id='null-plus'),
    pytest.param('null - 1', None, id='null-minus'),
    pytest.param('null * 2', None, id='null-times'),
    pytest.param('null / 2', None, id='null-divide'),
    pytest.param('1 + "a"', '1a', id='plus-joins-when-either-side-is-text'),
    pytest.param('-3 % 2', -1, id='remainder-keeps-the-sign-of-the-dividend'),
    pytest.param('1 / 0', math.inf, id='divide-by-zero-is-infinity'),
    # Truthiness follows JavaScript: empty arrays and objects are TRUE.
    pytest.param('![]', False, id='empty-array-is-true'),
    pytest.param('!{}', False, id='empty-object-is-true'),
    pytest.param('!""', True, id='empty-string-is-false'),
    pytest.param('!0', True, id='zero-is-false'),
    pytest.param('[] && 1', 1, id='and-returns-right-operand'),
    pytest.param('"" || 2', 2, id='or-returns-right-operand'),
    # type() names every type the language has.
    pytest.param('type("abc")', 'string', id='type-string'),
    pytest.param('type(1.5)', 'number', id='type-number'),
    pytest.param('type(false)', 'boolean', id='type-boolean'),
    pytest.param('type([1])', 'array', id='type-array'),
    pytest.param('type(missing_name)', 'null', id='type-of-missing'),
    # Indexing out of range is null, not an error and not Python's count-from-the-end.
    pytest.param('[1, 2][5]', None, id='index-out-of-range'),
    pytest.param('[1, 2][-1]', None, id='negative-index'),
    pytest.param('"ab"[1]', 'b', id='string-index'),
    # ``in`` on an array tests membership; on null it is null.
    pytest.param('"a" in ["a", "b"]', True, id='in-array'),
    pytest.param('"x" in null', None, id='in-null'),
    # Functions: numeric strings count as numbers (TSV cells are text) ...
    pytest.param('min(["0.5", "n/a", "-1"])', -1.0, id='min-of-numeric-strings'),
    pytest.param('max(["n/a"])', -math.inf, id='max-with-no-numbers'),
    pytest.param('min([])', math.inf, id='min-of-empty'),
    # ... and null or the wrong type gives null rather than raising.
    pytest.param('length(3)', None, id='length-of-a-number'),
    pytest.param('sorted(null)', None, id='sorted-null'),
    pytest.param('count(null, 1)', None, id='count-in-null'),
    pytest.param('count([1, 1], null)', None, id='count-of-null'),
    pytest.param('intersects("rad", ["rad", "arbitrary"])', ['rad'], id='intersects-single-value'),
    pytest.param('match(42, "4")', True, id='match-a-number'),
    pytest.param('match("a", "(")', None, id='match-invalid-pattern'),
    pytest.param('substr(12345, 1, 3)', '23', id='substr-of-a-number'),
    # A name the context does not define is null, like a missing field.
    pytest.param('missing_name', None, id='unknown-name'),
    pytest.param('missing_name.field', None, id='field-of-unknown-name'),
]


@pytest.mark.parametrize(('expression', 'expected'), EXTRA_VECTORS)
def test_extra_vectors(expression: str, expected: ty.Any) -> None:
    assert evaluate(parse(expression), el_namespace) == expected


def test_unknown_function_is_an_error_not_a_silent_null() -> None:
    """A function the language does not have (``len`` instead of ``length``) raises.

    The rule engine reads that as null, but here it must stay visible, or a typo in a
    rule would look like a passing check.
    """
    with pytest.raises(TypeError, match='Unknown function'):
        evaluate(parse('len([1, 2])'), el_namespace)


@pytest.mark.parametrize(
    ('expression', 'expected'),
    [
        # The NIfTI loader returns numpy arrays and scalars ...
        pytest.param('type(array)', 'array', id='numpy-array-is-an-array'),
        pytest.param('array[1]', 2, id='numpy-element-is-a-number'),
        pytest.param('type(scalar)', 'number', id='numpy-scalar-is-a-number'),
        pytest.param('scalar > 2', True, id='numpy-scalar-compares'),
        # ... and the TSV loader returns tuples.
        pytest.param('column == ["a", "b"]', True, id='tuple-equals-list'),
        pytest.param('length(column)', 2, id='tuple-has-a-length'),
        # A record such as ``associations`` is an object; a field holding None is absent.
        pytest.param('type(record)', 'object', id='record-is-an-object'),
        pytest.param('"bval" in record', True, id='record-field-present'),
        pytest.param('"events" in record', False, id='record-field-none-is-absent'),
    ],
)
def test_values_from_the_context_are_normalized(expression: str, expected: ty.Any) -> None:
    namespace = {
        'array': np.array([1, 2, 3], dtype=np.int16),
        'scalar': np.float32(2.5),
        'column': ('a', 'b'),
        'record': SimpleNamespace(events=None, bval='x'),
    }
    assert evaluate(parse(expression), el_namespace | namespace) == expected


def test_in_does_not_modify_a_namespace() -> None:
    """``".git" in namespace`` must not insert a key (bidsschematools reads dots as paths)."""
    namespace = Namespace({'a': {'b': 1}})
    assert evaluate(parse('".git" in ns'), el_namespace | {'ns': namespace}) is False
    assert list(namespace.keys()) == ['a']


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (None, False),
        (False, False),
        (0, False),
        (math.nan, False),
        ('', False),
        ([], True),
        ({}, True),
        ('0', True),
        (SimpleNamespace(), True),
    ],
)
def test_truthy_follows_javascript(value: ty.Any, expected: bool) -> None:
    assert truthy(value) is expected
