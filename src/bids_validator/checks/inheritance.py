"""Inherited metadata: whether a deeper JSON file changes a value set above it.

BIDS lets one JSON file describe many recordings: ``task-rest_bold.json`` at the
dataset root applies to every ``*_task-rest_bold.nii.gz`` below it, and a JSON file
closer to a recording can add to it or change it (the inheritance principle). The
nearest value is the one that applies. Changing a value that a file above already set
is allowed, but it is usually a mistake, so the reference validator warns about it
(``SIDECAR_FIELD_OVERRIDE``, from ``loadSidecar`` in ``src/schema/context.ts``).

The chain of JSON files a recording inherits from is found once per file, by
:attr:`.context.Context.sidecar_files`.
"""

# Lets type hints name classes that are only imported for type checkers (below).
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..context import ValidationError, load_json
from ..issues import Issue, IssueDefinition, Severity
from .values import json_equal

# Imported only for type hints; never imported when the program runs.
if TYPE_CHECKING:
    from ..context import Context

# The names other modules are meant to import from this one.
__all__ = ['SIDECAR_FIELD_OVERRIDE', 'inheritance_issues']

# --- what this module reports --------------------------------------------
#
# Not defined by the schema; the reference validator's definition (src/issues/list.ts).

# A deeper JSON file changes a value a JSON file above it set.
SIDECAR_FIELD_OVERRIDE = IssueDefinition(
    'SIDECAR_FIELD_OVERRIDE',
    Severity.WARNING,
    'Sidecar files should not override values assigned at a higher level.',
)


def inheritance_issues(context: Context) -> list[Issue]:
    """Warn where a deeper JSON file changes a value set by a JSON file above it.

    Reported on the deeper file, once per data file that inherits both. Values are
    compared by content, so the same list written twice is not an override.

    Parameters
    ----------
    context : Context
        A file. A ``.json`` file has no chain: it is a sidecar, not something that has
        one.

    Returns
    -------
    list of Issue
        One ``SIDECAR_FIELD_OVERRIDE`` per changed key.

    """
    try:
        chain = context.sidecar_files
    except ValidationError:
        return []  # ambiguous: reported by the integrity checks
    applied: dict[str, Any] = {}  # key -> the value that applies (the nearest)
    origin: dict[str, str] = {}  # key -> the file that value comes from
    issues: list[Issue] = []
    for json in chain:  # nearest first
        try:
            contents = load_json(json)
        except ValidationError:
            continue  # a broken JSON file is reported by the integrity checks
        for key, value in contents.items():
            if key not in applied:
                applied[key] = value
                origin[key] = json.relative_path
            elif not json_equal(applied[key], value):
                issues.append(
                    SIDECAR_FIELD_OVERRIDE.make_issue(
                        origin[key],
                        sub_code=key,
                        message=(
                            f'{key} = {applied[key]!r} overrides {value!r} '
                            f'from {json.relative_path}'
                        ),
                    )
                )
    return issues
