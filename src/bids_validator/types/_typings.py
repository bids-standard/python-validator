__all__ = (
    'Self',
    'TYPE_CHECKING',
    'Any',
    'Iterable',
    'TracebackType',
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType
    from typing import Any, Self
else:

    def __getattr__(name: str):
        match name:
            case 'Iterable':
                return __import__('collections.abc').Iterable
            case 'TracebackType':
                return __import__('types').TracebackType
            case _:
                return getattr(__import__('typing'), name)

        msg = f'Module {__name__!r} has no attribute {name!r}'
        raise AttributeError(msg)
