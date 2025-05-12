"""Utilities for generating validation context classes from a BIDS schema.

For default contexts based on the installed BIDS schema, use the `context` module.
These functions allow generating classes from alternative schemas.

Basic usage:

.. python::

    from bids_validator.context_generator import get_schema, load_schema_into_namespace

    schema = get_schema('https://bids-specification.readthedocs.io/en/stable/schema.json')
    load_schema_into_namespace(schema['meta']['context'], globals(), 'Context')
"""

import json
from typing import Any, Union

import attrs
import bidsschematools as bst
import bidsschematools.schema

LATEST_SCHEMA_URL = 'https://bids-specification.readthedocs.io/en/latest/schema.json'
STABLE_SCHEMA_URL = 'https://bids-specification.readthedocs.io/en/stable/schema.json'


def get_schema(url: Union[str, None] = None) -> bst.types.Namespace:
    """Load a BIDS schema from a URL or return the bundled schema if no URL is provided.

    This function utilizes the ``universal_pathlib`` package to handle various URL schemes.
    To enable non-default functionality, install the required dependencies using::

        pip install fsspec[http]  # for HTTP/HTTPS URLs

    Typically, ``fsspec[<schema>]`` will work for ``<schema>://...`` URLs.

    Parameters
    ----------
    url : str | None
        The path or URL to load the schema from. If None, the bundled schema is returned.
        The strings 'latest' and 'stable' are also accepted as shortcuts.

    Returns
    -------
    dict[str, Any]
        The loaded schema as a dictionary.

    """
    if url is None:
        return bst.schema.load_schema()

    if url == 'latest':
        url = LATEST_SCHEMA_URL
    elif url == 'stable':
        url = STABLE_SCHEMA_URL

    from upath import UPath

    url = UPath(url)

    try:
        schema_text = UPath(url).read_text()
    except ImportError as e:
        message = (
            f'Unable to load {url}. This can probably be fixed '
            f'by depending on "fsspec[{url.proto}]".'
        )
        raise ImportError(message) from e

    return bst.types.Namespace(json.loads(schema_text))


def snake_to_pascal(val: str) -> str:
    """Convert snake_case string to PascalCase."""
    return ''.join(sub.capitalize() for sub in val.split('_'))


def typespec_to_type(name: str, typespec: dict[str, Any]) -> tuple[type, dict[str, Any]]:
    """Convert JSON-schema style specification to type and metadata dictionary."""
    tp = typespec.get('type')
    if not tp:
        raise ValueError(f'Invalid typespec: {json.dumps(typespec)}')
    metadata = {key: typespec[key] for key in ('name', 'description') if key in typespec}
    if tp == 'object':
        properties = typespec.get('properties')
        if properties:
            type_ = create_attrs_class(name, properties=properties, metadata=metadata)
        else:
            type_ = dict[str, Any]
    elif tp == 'array':
        if 'items' in typespec:
            subtype, md = typespec_to_type(name, typespec['items'])
        else:
            subtype = Any
        type_ = list[subtype]
    else:
        type_ = {
            'number': float,
            'string': str,
            'integer': int,
        }[tp]
    return type_, metadata


def _type_name(tp: type) -> str:
    try:
        return tp.__name__
    except AttributeError:
        return str(tp)


def create_attrs_class(
    class_name: str,
    properties: dict[str, Any],
    metadata: dict[str, Any],
) -> type:
    """Dynamically create an attrs class with the given properties.

    Parameters
    ----------
    class_name
        The name of the class to create.
    properties
        A dictionary of property names and their corresponding schema information.
        If a nested object is encountered, a nested class is created.
    metadata
        A short description of the class, included in the docstring.

    Returns
    -------
    cls : type
        The dynamically created attrs class.

    """
    attributes = {}
    for prop_name, prop_info in properties.items():
        type_, md = typespec_to_type(prop_name, prop_info)
        attributes[prop_name] = attrs.field(
            type=type_, repr=prop_name != 'schema', default=None, metadata=md
        )

    return attrs.make_class(
        snake_to_pascal(class_name),
        attributes,
        class_body={
            '__doc__': f"""\
{metadata.get('description', '')}

attrs data class auto-generated from BIDS schema

Attributes
----------
"""
            + '\n'.join(
                f'{k}: {_type_name(v.type)}\n\t{v.metadata["description"]}'
                for k, v in attributes.items()
            ),
        },
    )


def generate_attrs_classes_from_schema(
    schema: dict[str, Any],
    root_class_name: str,
) -> type:
    """Generate attrs classes from a JSON schema.

    Parameters
    ----------
    schema : dict[str, Any]
        The JSON schema to generate classes from. Must contain a 'properties' field.
    root_class_name : str
        The name of the root class to create.

    Returns
    -------
    cls : type
        The root class created from the schema.

    """
    if 'properties' not in schema:
        raise ValueError("Invalid schema: 'properties' field is required")

    type_, _ = typespec_to_type(root_class_name, schema)
    return type_


def populate_namespace(attrs_class: type, namespace: dict[str, Any]) -> None:
    """Populate a namespace with nested attrs classes.

    Parameters
    ----------
    attrs_class : type
        The root attrs class to add to the namespace.
    namespace : dict[str, Any]
        The namespace to populate with nested classes.

    """
    for attr in attrs.fields(attrs_class):
        attr_type = attr.type

        if attrs.has(attr_type):
            namespace[attr_type.__name__] = attr_type
            populate_namespace(attr_type, namespace)


def load_schema_into_namespace(
    schema: dict[str, Any],
    namespace: dict[str, Any],
    root_class_name: str,
) -> None:
    """Load a JSON schema into a namespace as attrs classes.

    Intended to be used with globals() or locals() to create classes in the current module.

    Parameters
    ----------
    schema : dict[str, Any]
        The JSON schema to load into the namespace.
    namespace : dict[str, Any]
        The namespace to load the schema into.
    root_class_name : str
        The name of the root class to create.

    """
    attrs_class = generate_attrs_classes_from_schema(schema, root_class_name)
    namespace[root_class_name] = attrs_class
    populate_namespace(attrs_class, namespace)
