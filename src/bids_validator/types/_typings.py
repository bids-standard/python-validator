__all__ = (
    'Self',
    'TYPE_CHECKING',
    'Any',
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Self
else:

    def __getattr__(name: str):
        if name in __all__:
            import typing

            return getattr(typing, name)

        msg = f'Module {__name__!r} has no attribute {name!r}'
        raise AttributeError(msg)
