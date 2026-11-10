"""Tests for reading something out of the schema once per schema."""

from bidsschematools.types.namespace import Namespace

from bids_validator.checks.schema_cache import once_per_schema


def test_an_answer_is_worked_out_once_per_schema() -> None:
    calls: list[Namespace] = []

    @once_per_schema
    def count_rules(schema: Namespace) -> int:
        calls.append(schema)
        return len(schema['rules'])

    first = Namespace({'rules': {'a': 1}})
    second = Namespace({'rules': {'a': 1, 'b': 2}})
    assert count_rules(first) == 1
    assert count_rules(first) == 1
    assert count_rules(second) == 2
    assert calls == [first, second]
