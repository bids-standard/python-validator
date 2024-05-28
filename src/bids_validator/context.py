"""Validation context for schema-based BIDS validation."""

from .context_generator import get_schema, load_schema_into_namespace

schema = get_schema()
load_schema_into_namespace(schema['meta']['context']['context'], globals(), 'Context')


__all__ = [  # noqa: F822
    'Context',
    'Schema',
    'Dataset',
    'Dataset_description',
    'Tree',
    'Subjects',
    'Subject',
    'Sessions',
    'Entities',
    'Sidecar',
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
    'Columns',
    'Json',
    'Gzip',
    'Nifti_header',
    'Dim_info',
    'Xyzt_units',
    'Ome',
    'Tiff',
]
