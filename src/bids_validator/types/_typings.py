__all__ = (
    'Self',
    'TYPE_CHECKING',
    'Any',
    'Iterable',
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, Self
else:

    def __getattr__(name: str):
        if name == 'Iterable':
            from collections.abc import Iterable

            return Iterable
        if name in __all__:
            import typing

            return getattr(typing, name)

        msg = f'Module {__name__!r} has no attribute {name!r}'
        raise AttributeError(msg)
