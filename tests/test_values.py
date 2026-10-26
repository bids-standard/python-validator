"""Tests for checking a metadata value against its schema definition."""

import typing as ty

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator.values import json_equal, value_errors

FORMATS = {
    'index': {'pattern': '[0-9]+'},
    'bids_uri': {'pattern': 'bids:[0-9a-zA-Z/#:?_\\-.]+'},
    'participant_relative': {'pattern': '(?!/)(?!sub-)[0-9a-zA-Z+/_\\-.]+'},
}


@pytest.mark.parametrize(
    ('value', 'definition', 'expected'),
    [
        pytest.param(2.0, {'type': 'number'}, [], id='number'),
        pytest.param('2.0', {'type': 'number'}, ['must be number'], id='text-is-not-a-number'),
        pytest.param(True, {'type': 'number'}, ['must be number'], id='true-is-not-a-number'),
        pytest.param(3.0, {'type': 'integer'}, [], id='integral-float-is-integer'),
        pytest.param(3.5, {'type': 'integer'}, ['must be integer'], id='fraction-is-not-integer'),
        pytest.param('x', {'type': ['string', 'null']}, [], id='type-list'),
        pytest.param('raw', {'enum': ['raw', 'derivative']}, [], id='enum-member'),
        pytest.param(
            'study',
            {'enum': ['raw', 'derivative']},
            ['must be equal to one of the allowed values'],
            id='enum-outsider',
        ),
        pytest.param(
            1,
            {'enum': [True]},
            ['must be equal to one of the allowed values'],
            id='one-is-not-true',
        ),
        pytest.param(
            0, {'type': 'number', 'exclusiveMinimum': 0}, ['must be > 0'], id='exclusive-minimum'
        ),
        pytest.param(-1, {'type': 'number', 'minimum': 0}, ['must be >= 0'], id='minimum'),
        pytest.param(5, {'type': 'number', 'maximum': 1}, ['must be <= 1'], id='maximum'),
        pytest.param(
            [],
            {'type': 'array', 'minItems': 1},
            ['must NOT have fewer than 1 items'],
            id='min-items',
        ),
        pytest.param(
            [1, 2, 3],
            {'type': 'array', 'maxItems': 2},
            ['must NOT have more than 2 items'],
            id='max-items',
        ),
        pytest.param(
            ['a', 1],
            {'type': 'array', 'items': {'type': 'string'}},
            ['/1 must be string'],
            id='item-type-with-position',
        ),
        pytest.param(
            {'Name': 'x'},
            {'type': 'object', 'required': ['Name', 'Version']},
            ["must have required property 'Version'"],
            id='required-property',
        ),
        pytest.param(
            {'a': 1, 'b': 2},
            {'type': 'object', 'properties': {'a': {}}, 'additionalProperties': False},
            ['must NOT have additional properties'],
            id='additional-properties',
        ),
        pytest.param('bids::sub-01/x', {'type': 'string', 'format': 'bids_uri'}, [], id='format'),
        pytest.param(
            'sub-01/x',
            {'type': 'string', 'format': 'bids_uri'},
            ['must match format "bids_uri"'],
            id='format-mismatch',
        ),
        # Searched, not matched, as ajv does: an unanchored pattern occurs somewhere.
        pytest.param(
            '/sub-01',
            {'type': 'string', 'format': 'participant_relative'},
            [],
            id='format-searched',
        ),
        pytest.param('x', {'type': 'string', 'format': 'unknown'}, [], id='unknown-format'),
        pytest.param(
            'x',
            {'anyOf': [{'type': 'number'}, {'type': 'array'}]},
            ['must be number', 'must be array', 'must match a schema in anyOf'],
            id='any-of-reports-every-branch',
        ),
        pytest.param(
            3, {'anyOf': [{'type': 'number'}, {'type': 'array'}]}, [], id='any-of-passes'
        ),
        # ajv stops at the first failing keyword: type before bounds.
        pytest.param(
            'x', {'type': 'number', 'minimum': 0}, ['must be number'], id='first-error-only'
        ),
    ],
)
def test_value_errors(value: ty.Any, definition: dict[str, ty.Any], expected: list[str]) -> None:
    assert value_errors(value, definition, FORMATS) == expected


def test_real_definitions(schema: Namespace) -> None:
    """Against the schema's own definitions and formats."""
    metadata, formats = schema.objects.metadata, schema.objects.formats
    assert value_errors(2.0, metadata.RepetitionTime, formats) == []
    assert value_errors(-2.0, metadata.RepetitionTime, formats) == ['must be > 0']
    assert value_errors('Me', metadata.Authors, formats) == ['must be array']
    assert value_errors(['Me'], metadata.Authors, formats) == []


@pytest.mark.parametrize(
    ('a', 'b', 'equal'),
    [
        (1, 1.0, True),
        (True, 1, False),
        ([1, 2], [1, 2], True),
        ([1, 2], [2, 1], False),
        ({'a': [1]}, {'a': [1]}, True),
        ('1', 1, False),
        (None, None, True),
    ],
)
def test_json_equal(a: ty.Any, b: ty.Any, equal: bool) -> None:
    assert json_equal(a, b) is equal
