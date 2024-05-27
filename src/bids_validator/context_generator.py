from typing import Any

import attrs
import bidsschematools as bst
import bidsschematools.schema
import httpx

LATEST_SCHEMA_URL = 'https://bids-specification.readthedocs.io/en/latest/schema.json'
STABLE_SCHEMA_URL = 'https://bids-specification.readthedocs.io/en/stable/schema.json'


def get_schema(url: str | None = None) -> dict[str, Any]:
    """Load a BIDS schema from a URL or return the bundled schema if no URL is provided.

    Parameters
    ----------
    url : str | None
        The URL to load the schema from. If None, the bundled schema is returned.
        The strings 'latest' and 'stable' are also accepted as shortcuts.

    Returns
    -------
    Dict[str, Any]
        The loaded schema as a dictionary.

    """
    if url is None:
        return bst.schema.load_schema()

    if url == 'latest':
        url = LATEST_SCHEMA_URL
    elif url == 'stable':
        url = STABLE_SCHEMA_URL

    with httpx.Client() as client:
        return client.get(url).json()


def create_attrs_class(
    class_name: str, description: str | None, properties: dict[str, Any]
) -> type:
    """Dynamically create an attrs class with the given properties.

    Parameters
    ----------
    class_name : str
        The name of the class to create.
    description : str | None
        A short description of the class, included in the docstring.
    properties : Dict[str, Any]
        A dictionary of property names and their corresponding schema information.
        If a nested object is encountered, a nested class is created.

    Returns
    -------
    cls : type
        The dynamically created attrs class.

    """
    attributes = {}
    for prop_name, prop_info in properties.items():
        prop_type = prop_info.get('type')

        if prop_type == 'object':
            nested_class = create_attrs_class(
                prop_name.capitalize(),
                prop_info.get('description'),
                prop_info.get('properties', {}),
            )
            attributes[prop_name] = attrs.field(type=nested_class, default=None)
        elif prop_type == 'array':
            item_info = prop_info.get('items', {})
            item_type = item_info.get('type')

            if item_type == 'object':
                nested_class = create_attrs_class(
                    prop_name.capitalize(),
                    item_info.get('description'),
                    item_info.get('properties', {}),
                )
                attributes[prop_name] = attrs.field(type=list[nested_class], default=None)
            else:
                # Default to List[Any] for arrays of simple types
                attributes[prop_name] = attrs.field(type=list[Any], default=None)
        else:
            # Default to Any for simple types
            attributes[prop_name] = attrs.field(type=Any, default=None)

    return attrs.make_class(
        class_name,
        attributes,
        class_body={
            '__doc__': f"""\
{description}

attrs data class auto-generated from BIDS schema

Attributes
----------
{''.join([f'{k}: {v.type.__name__}\n' for k, v in attributes.items()])}
"""
        },
    )


def generate_attrs_classes_from_schema(
    schema: dict[str, Any],
    root_class_name: str,
) -> type:
    """Generate attrs classes from a JSON schema.

    Parameters
    ----------
    schema : Dict[str, Any]
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

    return create_attrs_class(
        root_class_name,
        schema.get('description'),
        schema['properties'],
    )


def populate_namespace(attrs_class: type, namespace: dict[str, Any]) -> None:
    """Populate a namespace with nested attrs classes.

    Parameters
    ----------
    attrs_class : type
        The root attrs class to add to the namespace.
    namespace : Dict[str, Any]
        The namespace to populate with nested classes.

    """
    for attr in attrs_class.__attrs_attrs__:
        attr_type = attr.type

        if isinstance(attr_type, type) and hasattr(attr_type, '__attrs_attrs__'):
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
    schema : Dict[str, Any]
        The JSON schema to load into the namespace.
    namespace : Dict[str, Any]
        The namespace to load the schema into.
    root_class_name : str
        The name of the root class to create.

    """
    attrs_class = generate_attrs_classes_from_schema(schema, root_class_name)
    namespace[root_class_name] = attrs_class
    populate_namespace(attrs_class, namespace)
