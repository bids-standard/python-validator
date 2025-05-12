"""Validation context for schema-based BIDS validation."""

from ._context import get_schema, load_schema_into_namespace

schema = get_schema()
load_schema_into_namespace(schema.meta.context, globals(), 'Context')


__all__ = [  # noqa: F822
    'Context',
    'Dataset',
    'Subjects',
    'Subject',
    'Sessions',
    'Associations',
    'Events',
    'Aslcontext',
    'M0scan',
    'Magnitude',
    'Magnitude1',
    'Bval',
    'Bvec',
    'Channels',
    'Coordsystem',
    'Gzip',
    'NiftiHeader',
    'DimInfo',
    'XyztUnits',
    'Ome',
    'Tiff',
]
