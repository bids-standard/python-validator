"""Work something out from the schema once, instead of once for every file.

The checks ask the schema the same questions for every file of a dataset: which
filename rules exist, which extensions name a directory recording, which rules have
selectors. The answers depend only on the schema, so a function that works one of them
out is decorated with :func:`once_per_schema`: it then runs once per schema, and every
later call returns the answer it already has.
"""

# Lets a type hint name a class before Python has defined it (``Namespace`` below is only
# imported for type checkers). Without it, annotations are evaluated when the function is
# defined.
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

# TYPE_CHECKING is False when the program runs and True only for a type checker (mypy).
# Imports placed under it cost nothing at run time and cannot cause import cycles; they
# exist only so the type hints can name these classes.
if TYPE_CHECKING:
    from bidsschematools.types.namespace import Namespace

# The names other modules are meant to import from this one (``from x import *`` also
# imports only these). Anything else here is internal.
__all__ = ['once_per_schema']

# "Some type": whatever the decorated function returns, the decorated version returns the
# same type. This lets mypy check the callers of a decorated function.
T = TypeVar('T')


def once_per_schema(function: Callable[[Namespace], T]) -> Callable[[Namespace], T]:
    """Decorate a function of the schema alone, so it runs once per schema.

    Writing ``@once_per_schema`` above a function is the same as writing
    ``function = once_per_schema(function)`` after it: the function is replaced by
    ``remembered`` below, which keeps the original and a small table of answers.

    A bidsschematools ``Namespace`` cannot be a dictionary key (it is not hashable), so
    each answer is kept under the schema's ``id()``, together with the schema itself.
    Keeping the schema keeps it alive, so its ``id()`` can never be given to another
    schema while the answer is stored.

    Parameters
    ----------
    function : callable
        Takes the schema, returns anything. It must not depend on anything else.

    Returns
    -------
    callable
        The same function, remembering its answer for each schema it is given.

    """
    answers: dict[int, tuple[Namespace, T]] = {}

    # Copies the name and docstring of ``function`` onto ``remembered``, so error
    # messages and help() still show the original function.
    @functools.wraps(function)
    def remembered(schema: Namespace) -> T:
        known = answers.get(id(schema))
        if known is None or known[0] is not schema:
            known = answers[id(schema)] = (schema, function(schema))
        return known[1]

    return remembered
