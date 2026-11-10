"""Tests for where the codes are defined: in the schema, or beside the checks that report them.

The rule is one place per code. A code the schema defines (in ``rules.errors``) is read
from the schema; any other code is written out once, as an ``IssueDefinition``, in the
check module that reports it.
"""

import re
from pathlib import Path
from types import ModuleType

import pytest
from bidsschematools.types.namespace import Namespace

from bids_validator import context
from bids_validator.checks import (
    expressions,
    fields,
    filenames,
    inheritance,
    integrity,
    tables,
)
from bids_validator.issues import IssueDefinition

CHECK_MODULES = (
    integrity,
    inheritance,
    filenames,
    expressions,
    fields,
    tables,
)


def definitions(module: ModuleType) -> dict[str, IssueDefinition]:
    """The definitions a module writes out, by the name they are given there."""
    return {
        name: value for name, value in vars(module).items() if isinstance(value, IssueDefinition)
    }


def schema_codes(schema: Namespace) -> set[str]:
    errors = schema['rules']['errors']
    return {str(errors[name]['code']) for name in errors}


@pytest.mark.parametrize('module', CHECK_MODULES, ids=lambda module: module.__name__)
def test_each_definition_is_named_after_its_code(module: ModuleType) -> None:
    for name, definition in definitions(module).items():
        assert name == definition.code
        assert definition.reason


def test_no_code_is_defined_twice() -> None:
    codes = [
        definition.code for module in CHECK_MODULES for definition in definitions(module).values()
    ]
    assert len(codes) == len(set(codes))


def test_no_code_the_schema_defines_is_written_out(schema: Namespace) -> None:
    """A code in rules.errors must be read from the schema, not copied into a module."""
    written = {
        definition.code for module in CHECK_MODULES for definition in definitions(module).values()
    }
    assert not written & schema_codes(schema)


def test_each_module_writes_out_the_codes_it_reports() -> None:
    assert set(definitions(filenames)) == {
        'ENTITY_WITH_NO_LABEL',
        'INVALID_ENTITY_LABEL',
        'MISSING_REQUIRED_ENTITY',
        'ENTITY_NOT_IN_RULE',
        'MISSING_DATATYPE',
        'DATATYPE_MISMATCH',
        'EXTENSION_MISMATCH',
        'INVALID_LOCATION',
        'FILENAME_MISMATCH',
        'ALL_FILENAME_RULES_HAVE_ISSUES',
        'CASE_COLLISION',
    }
    assert set(definitions(expressions)) == {'CHECK_ERROR'}
    assert set(definitions(inheritance)) == {'SIDECAR_FIELD_OVERRIDE'}
    assert set(definitions(fields)) == {
        'SIDECAR_KEY_REQUIRED',
        'SIDECAR_KEY_RECOMMENDED',
        'JSON_KEY_REQUIRED',
        'JSON_KEY_RECOMMENDED',
    }


def test_the_schema_entries_the_modules_read_exist(schema: Namespace) -> None:
    """Every ``rules.errors`` entry a module reads by name is in the schema."""
    read = set()
    for module in CHECK_MODULES:
        source = Path(str(module.__file__)).read_text()
        read |= set(re.findall(r"\['errors'\]\['(\w+)'\]", source))
        read |= set(re.findall(r"_schema_error\(\s*\w+(?:\.\w+)*,\s*'(\w+)'", source))
    read |= set(integrity.LOADER_ERRORS_IN_SCHEMA.values())
    assert read == {
        'NotIncluded',
        'EmptyFile',
        'NiftiHeaderUnreadable',
        'JsonInvalid',
        'InvalidJsonEncoding',
        'JsonSchemaValidationError',
    }
    assert read <= set(schema['rules']['errors'].keys())


def test_every_code_a_loader_raises_is_reported() -> None:
    """The context's loaders raise codes; integrity must know each one."""
    source = Path(str(context.__file__)).read_text()
    raised = set(re.findall(r"ValidationError\(\s*'([A-Z_]+)'", source))
    known = set(integrity.LOADER_ERRORS) | set(integrity.LOADER_ERRORS_IN_SCHEMA)
    assert raised == known
