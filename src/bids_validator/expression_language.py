"""Implementation of the BIDS schema expression language.

The schema writes its rules as small expressions, such as ``size > 150`` or
``"Units" in sidecar``. ``bidsschematools.expressions.parse`` turns the text into a
tree; :func:`evaluate` walks that tree against a file's context and returns a value.

The language is defined in the schema's own documentation (``src/schema/README.md``
in bids-specification, section "Expressions") and pinned by the test vectors in
``schema.meta.expression_tests``. Where the two disagree, the test vectors win,
because they are what every implementation is checked against.

Three properties of the language are easy to get wrong in Python:

* **Missing values are null.** ``sidecar.MissingValue`` is ``null``, and ``null``
  propagates through most operations (``null + 1`` is ``null``) instead of raising.
* **Truth follows JavaScript.** An empty array or object is true; ``null``, ``0``,
  ``NaN`` and the empty string are false. See :func:`truthy`.
* **Values are plain.** The language knows null, booleans, numbers, strings, arrays
  and objects. The context hands over numpy arrays (NIfTI headers) and tuples (TSV
  columns), so every value read from the context goes through :func:`normalize`.
"""

import math
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from typing import Any, TypeVar
from typing import Literal as L

import numpy as np

# The schema's own parser: ``bst_expr.parse('size > 150')`` returns a tree of nodes
# (``BinOp(op='>', lh='size', rh=150)``) that :func:`evaluate` walks.
from bidsschematools import expressions as bst_expr

from bids_validator.context import Context

# "Some value type": in ``count_(array: list[T], val: T)`` the value counted has the type
# of the array's items. Only used by type hints.
T = TypeVar('T', bound=str | int | float)


def truthy(value: Any) -> bool:
    """Return whether a value counts as true in the expression language.

    The rules follow JavaScript, which the schema's reference implementation uses,
    and differ from Python's in two ways: an empty array or object is TRUE, and
    ``NaN`` is FALSE.

    Parameters
    ----------
    value : Any
        Any value an expression can produce

    Returns
    -------
    bool
        False for null, false, 0, NaN and the empty string; True for everything else

    """
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return not (value == 0 or math.isnan(value))
    if isinstance(value, str):
        return value != ''
    return True


def normalize(value: Any) -> Any:
    """Convert a value read from the context into a plain expression-language value.

    Loaders return numpy arrays and numpy scalars (``nifti_header.dim``) and tuples
    (TSV columns). The language only knows arrays, so both become lists, and numpy
    numbers become Python numbers. Without this, ``type(nifti_header.dim)`` is not
    ``"array"`` and comparing a column to a list literal is always false.

    Parameters
    ----------
    value : Any
        A value as the context returned it

    Returns
    -------
    Any
        The same value, with tuples and numpy arrays as lists and numpy scalars as
        Python numbers

    """
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return [normalize(item) for item in value]
    return value


def as_number(val: Any) -> int | float | None:
    """Coerce a value to a number, or return None if it is not one.

    Numeric strings count, because TSV cells are read as text: the onset column of
    an events file arrives as ``["0.5", "1.0", "n/a"]``.

    Parameters
    ----------
    val : Any
        value to coerce

    Returns
    -------
    int | float | None
        The number, or None for null, non-numeric strings and other types

    """
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return None
    return None


def numeric_values(arg: list[Any]) -> list[int | float]:
    """Keep the numeric values of a list, converting numeric strings.

    Parameters
    ----------
    arg : list
        list that may contain elements with a list of types

    Returns
    -------
    list
        list containing just numeric values, with ``n/a`` and NaN dropped

    """
    numbers = (as_number(val) for val in arg)
    return [num for num in numbers if num is not None and not math.isnan(num)]


def is_numeric(val: Any) -> bool:
    """Determine if a value can be coerced to numeric.

    Parameters
    ----------
    val : Any
        value to check

    Returns
    -------
    bool
        Indicates whether the value can be coerced

    """
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def in_(a: Any, b: Any) -> bool | None:
    """Object lookup, true if LHS is a key of the RHS object.

    The schema also uses ``in`` on arrays (``"micr" in dataset.modalities``), meaning
    "is a member of", so arrays and strings test membership. Any other object, such
    as the ``associations`` record, tests for a field that is present and not null.

    Parameters
    ----------
    a : Any
        The key or value to look for
    b : Any
        The object, array or string to look in

    Returns
    -------
    bool | None
        null if ``b`` is null, otherwise whether ``a`` was found

    """
    if b is None:
        return None
    if isinstance(b, Mapping):
        # Test the keys view, not the mapping: a bidsschematools Namespace reads a
        # dotted key as a path, and ``".git" in namespace`` inserts an empty key.
        try:
            return a in b.keys()  # noqa: SIM118
        except TypeError:  # an unhashable key
            return False
    if isinstance(b, (list, str)):
        try:
            return a in b
        except TypeError:  # a non-string looked up in a string
            return False
    if isinstance(a, str):
        return getattr(b, a, None) is not None
    return False


def allequal_(array1: list[object] | None, array2: list[object] | None) -> bool:
    """Determine if two arrays have the same length and paired elements are equal.

    Parameters
    ----------
    array1 : list | None
        list of values
    array2 : list | None
        list of values

    Returns
    -------
    bool
        Indicates whether lists are all equal

    """
    if array1 is None or array2 is None:
        return False

    if len(array1) != len(array2):
        return False

    return all(a == b for a, b in zip(array1, array2, strict=True))


def count_(array: list[T] | None, val: T | None) -> int | None:
    """Count the number of times a value is found in an array.

    Parameters
    ----------
    array : list | None
        Array of elements
    val : Any
        value to count

    Returns
    -------
    int | None
        Number of elements in an array equal to val, null if either argument is null

    """
    if not isinstance(array, list) or val is None:
        return None
    return array.count(val)


def index_(arg: Sequence[T] | None, val: T | None) -> int | None:
    """Find the first element of an array or string that is equal to the value provided.

    Parameters
    ----------
    arg : str | list | None
        Array of elements or string
    val : Any | None
        Value to find

    Returns
    -------
    int | None
        Index of first element in an array equal to val, null if not found

    """
    if arg is None or val is None:
        return None

    if val in arg:
        return arg.index(val)

    return None


def intersects_(a: Any, b: Any) -> list[Any] | bool:
    """Find the common values in two arrays.

    A single value is treated as an array of one, as the reference implementation
    does, so ``intersects(sidecar.Units, ["rad"])`` works whether ``Units`` holds a
    string or a list.

    Parameters
    ----------
    a : list | None
        Array one
    b : list | None
        Array two

    Returns
    -------
    list | bool
        The intersection of arrays a and b, or false if there are no shared values

    """
    if a is None or b is None:
        return False

    a = a if isinstance(a, list) else [a]
    b = b if isinstance(b, list) else [b]

    # Membership by ``==`` rather than a set, so unhashable elements cannot raise.
    res = [item for item in a if item in b]

    if res:
        return res

    return False


def length_(arg: Any) -> int | None:
    """Find the number of elements in an array, or characters in a string.

    Parameters
    ----------
    arg : list | str | None
        An Array or a string

    Returns
    -------
    int | None
        Number of elements, null for anything that is not an array or a string

    """
    if isinstance(arg, (list, str)):
        return len(arg)

    return None


def match_(arg: Any, pattern: Any) -> bool | None:
    """Evaluate whether a regular expression pattern appears in a string.

    Parameters
    ----------
    arg : str | None
        The string to evaluate
    pattern : str | None
        The pattern to match

    Returns
    -------
    bool | None
        true if arg matches the regular expression pattern (anywhere in string),
        null if arg is null or the pattern is not a valid regular expression

    """
    if arg is None:
        return None
    elif pattern is None:
        return False

    try:
        res = re.search(str(pattern), str(arg))
    except re.error:
        return None
    return res is not None


def max_(arg: int | float | list[Any] | None) -> int | float | None:
    """Find the largest numeric value in an array.

    Parameters
    ----------
    arg : list | None
        The array to evaluate

    Returns
    -------
    int | float | None
        The largest non-n/a value in an array; minus infinity if there is none, as in
        the reference implementation

    """
    if arg is None:
        return None

    if not isinstance(arg, list):
        arg = [arg]

    return max(numeric_values(arg), default=-math.inf)


def min_(arg: int | float | list[Any] | None) -> int | float | None:
    """Find the smallest numeric value in an array.

    Parameters
    ----------
    arg : list | None
        The array to evaluate

    Returns
    -------
    int | float | None
        The smallest non-n/a value in an array; infinity if there is none, as in the
        reference implementation

    """
    if arg is None:
        return None

    if not isinstance(arg, list):
        arg = [arg]

    return min(numeric_values(arg), default=math.inf)


def sorted_(arg: list[T] | None, method: L['lexical', 'numeric'] | None = None) -> list[T] | None:
    """Return sorted input array.

    Defaults to type-determined sort.
    If method is “lexical”, or “numeric” use lexical or numeric sort.

    Parameters
    ----------
    arg : list | None
        Array to sort
    method : str | None, optional
        Method to sort by, can be "lexical" or "numeric", by default None

    Returns
    -------
    list | None
        The sorted values of the input array, null if the input is not an array

    """
    if not isinstance(arg, list):
        return None

    contains_str = any(isinstance(x, str) for x in arg)

    if method is None:
        if contains_str:
            return sorted_(arg, method='lexical')
        else:
            return sorted_(arg, method='numeric')

    if method == 'lexical':
        return sorted(arg, key=str)

    elif method == 'numeric':
        non_numeric_vals = {i: d for i, d in enumerate(arg) if not is_numeric(d)}
        if non_numeric_vals:
            numeric_vals = [d for d in arg if is_numeric(d)]
            sorted_vals = sorted_(numeric_vals, method='numeric') or []

            for key, val in non_numeric_vals.items():
                sorted_vals.insert(key, val)

            return sorted_vals
        else:
            return sorted(arg, key=float)


def substr_(arg: Any, start: int | None, end: int | None) -> str | None:
    """Extract a sub-string from an existing string.

    Parameters
    ----------
    arg : str | None
        String to evaluate
    start : int | None
        Start position
    end : int | None
        End position

    Returns
    -------
    str | None
        The portion of the input string spanning from start position to end position

    """
    if arg is not None and start is not None and end is not None:
        return str(arg)[start:end]

    return None


def type_(var: Any) -> str:
    """Evaluate the type of a variable.

    Parameters
    ----------
    var : Any
        Variable to evaluate

    Returns
    -------
    str
        One of "null", "boolean", "number", "string", "array" or "object". Anything
        that is not one of the first five, such as a parsed NIfTI header, is an object.

    """
    match normalize(var):
        case None:
            return 'null'
        case bool():
            return 'boolean'
        case int() | float():
            return 'number'
        case str():
            return 'string'
        case list():
            return 'array'
        case _:
            return 'object'


def unique_(arg: list[T] | None) -> list[T] | None:
    """Return the unique values of the input array, retaining their input order.

    Equal float and int values are not considered distinct.

    Parameters
    ----------
    arg : list | None
        Input list

    Returns
    -------
    list | None
        A list of the unique values form the input list

    """
    if arg is not None:
        return list(dict.fromkeys(arg))

    return None


def _null_propagating(
    func: Callable[[Any, Any], Any],
) -> Callable[[Any, Any], Any]:
    """Wrap a numeric operator so it follows the language's rules.

    ``null`` on either side gives ``null`` (``null + 1`` is ``null``), and an operand
    that is not a number gives ``null`` instead of raising. Numeric strings count as
    numbers, as they do in the reference implementation.
    """

    def apply(a: Any, b: Any) -> Any:
        if a is None or b is None:
            return None
        x, y = as_number(a), as_number(b)
        if x is None or y is None:
            return None
        return func(x, y)

    return apply


def _add(a: Any, b: Any) -> Any:
    """Add two numbers, or join two strings when either side is a string."""
    if a is None or b is None:
        return None
    if isinstance(a, str) or isinstance(b, str):
        return f'{a}{b}'
    return _null_propagating(operator.add)(a, b)


def _divide(a: int | float, b: int | float) -> float:
    """Divide, giving infinity or NaN for a zero divisor, as the reference does."""
    if b == 0:
        return math.nan if a == 0 or math.isnan(a) else math.copysign(math.inf, a)
    return a / b


def _modulo(a: int | float, b: int | float) -> int | float:
    """Remainder with the sign of the dividend, as the reference does (``-3 % 2 == -1``)."""
    if b == 0:
        return math.nan
    result = math.fmod(a, b)
    return int(result) if isinstance(a, int) and isinstance(b, int) else result


def _power(a: int | float, b: int | float) -> int | float:
    """Raise to a power, giving infinity or NaN where Python would raise or go complex."""
    try:
        result = a**b
    except (ZeroDivisionError, OverflowError):  # 0 ** -1, 10.0 ** 1000
        return math.inf
    if isinstance(result, complex):  # (-8) ** 0.5
        return math.nan
    return result


def _compare(func: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    """Wrap an ordering operator (``<``, ``<=``, ``>``, ``>=``).

    The schema's documentation states that comparing with ``null`` is false, like
    ``null == 1``. Two strings compare as text; anything else compares as numbers,
    and a value that is not a number makes the comparison false.
    """

    def compare(a: Any, b: Any) -> bool:
        if a is None or b is None:
            return False
        if isinstance(a, str) and isinstance(b, str):
            return func(a, b)
        x, y = as_number(a), as_number(b)
        if x is None or y is None:
            return False
        return func(x, y)

    return compare


# The binary operators the language has, from the operator's text to the function that
# computes it: ``evaluate`` looks up ``bin_ops['>']`` for ``size > 150`` and calls it
# with both sides. ``&&`` and ``||`` are not here: ``evaluate`` handles them itself,
# because they must not evaluate their right side when the left decides.
bin_ops: dict[str, Callable[[Any, Any], Any]] = {
    '+': _add,
    '-': _null_propagating(operator.sub),
    '*': _null_propagating(operator.mul),
    '/': _null_propagating(_divide),
    '%': _null_propagating(_modulo),
    '**': _null_propagating(_power),
    '==': operator.eq,
    '!=': operator.ne,
    '<': _compare(operator.lt),
    '<=': _compare(operator.le),
    '>': _compare(operator.gt),
    '>=': _compare(operator.ge),
    'in': in_,
}

# The one prefix operator, ``!`` (not), decided by the language's truth test.
right_ops: dict[str, Callable[[Any], Any]] = {'!': lambda value: not truthy(value)}

# The functions an expression may call, from their name in the schema to the Python
# function. Each Python name ends in ``_`` so it does not hide a Python built-in
# (``max_`` is the schema's ``max``, ``max`` stays Python's).
functions = {
    'allequal': allequal_,
    'count': count_,
    'index': index_,
    'intersects': intersects_,
    'length': length_,
    'match': match_,
    'max': max_,
    'min': min_,
    'sorted': sorted_,
    'substr': substr_,
    'type': type_,
    'unique': unique_,
}

# The language's three constant words, and the Python values they stand for.
vals = {
    'true': True,
    'false': False,
    'null': None,
}

# Every name an expression can use that is not about a file: the constants and the
# functions. ``interpret`` puts it in front of the file's context, so ``length`` is the
# function and ``sidecar`` is the file's sidecar.
el_namespace = vals | functions

# A unique "not found" marker for ``LookupProxy``: unlike None, no context attribute can
# ever be this object, so "absent" and "present but null" stay different.
_MISSING = object()


class LookupProxy:
    """Lookup proxy for context class.

    Looks a name up in each of several objects in turn (first ``el_namespace``, then the
    file's context) and returns the first match, so an expression sees one namespace.
    """

    def __init__(self, *objs: Mapping[str, Any] | Context) -> None:
        self.objs = objs

    def __getitem__(self, key: str) -> Any:
        for obj in self.objs:
            if isinstance(obj, Mapping):
                if key in obj:
                    return obj[key]
                continue
            # One getattr, not hasattr then getattr: a context property can do real
            # work (load a sidecar), and hasattr would do it twice.
            value = getattr(obj, key, _MISSING)
            if value is not _MISSING:
                return value
        raise AttributeError(key)

    # Provide either attr or item lookup
    __getattr__ = __getitem__


def _lookup(container: Any, key: Any) -> Any:
    """Read a field from an object, or null if it has no such field."""
    if isinstance(container, Mapping):
        return container.get(key)
    if isinstance(key, str):
        return getattr(container, key, None)
    return None


def evaluate(expr: bst_expr.ASTNode | float | str, namespace: object) -> Any:
    """Evaluate an expression, with a provided namespace for variable lookup."""
    match expr:
        case float() | int():
            return expr
        case str() if expr[0] == expr[-1] and expr[0] in ('"', "'"):
            return expr[1:-1]
        case str():
            # A name the context does not define is null, like any missing value.
            if isinstance(namespace, Mapping):
                return normalize(namespace.get(expr))
            try:
                return normalize(getattr(namespace, expr))
            except AttributeError:
                return None
        case bst_expr.Object():
            return {}
        case bst_expr.Array(elements=elements):
            return [evaluate(el, namespace) for el in elements]
        case bst_expr.Element(name=name, index=index):
            target = evaluate(name, namespace)
            key = evaluate(index, namespace)
            if isinstance(target, (list, str)):
                # Out of range (or negative) is null, as in the reference implementation,
                # rather than an error or Python's count-from-the-end.
                if isinstance(key, int) and not isinstance(key, bool) and 0 <= key < len(target):
                    return normalize(target[key])
                return None
            if target is None:
                return None
            return normalize(_lookup(target, key))
        case bst_expr.Property(name=name, field=field):
            base_object = evaluate(name, namespace)
            if base_object is None:
                return None
            return normalize(_lookup(base_object, field))
        case bst_expr.Function(name=name, args=args):
            func = evaluate(name, namespace)
            if not callable(func):
                raise TypeError(f'Unknown function {name!r}')
            return func(*[evaluate(arg, namespace) for arg in args])
        case bst_expr.BinOp(op=op, lh=lh, rh=rh):
            match op:
                # Short-circuiting operators return one of their operands, as in the
                # reference implementation: ``null && true`` is null, not false.
                case '||':
                    left = evaluate(lh, namespace)
                    return left if truthy(left) else evaluate(rh, namespace)
                case '&&':
                    left = evaluate(lh, namespace)
                    return evaluate(rh, namespace) if truthy(left) else left
                case _:
                    return bin_ops[op](evaluate(lh, namespace), evaluate(rh, namespace))
        case bst_expr.RightOp(op=op, rh=rh):
            return right_ops[op](evaluate(rh, namespace))
        case _:
            raise ValueError(f'Expression type {type(expr)} not supported.')


@lru_cache(maxsize=4096)
def parse(rule: str) -> bst_expr.ASTNode:
    """Parse an expression once; the same rule text is evaluated for every file."""
    return bst_expr.parse(rule)


def interpret(rule: str, context: Context) -> Any:
    """Interpret a rule from the schema in a given file context."""
    namespace = LookupProxy(el_namespace, context)
    expr = parse(rule)
    return evaluate(expr, namespace)
