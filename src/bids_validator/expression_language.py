import operator
import re
from typing import Any

from bidsschematools import expressions as bst_expr

true = True
false = False
null = None


def evaluate_arg(arg: Any) -> Any:
    """Evaluate an individual argument."""
    if isinstance(arg, str):
        return eval(arg) # noqa: S307

    return arg


def filter_strs(arg: list) -> list:
    """Filter non-numeric values from a list.

    Parameters
    ----------
    arg : list
        list that may contain elements with a list of types

    Returns
    -------
    list
        list containing just numeric (i.e. int and float) values

    """
    return [val for val in arg if isinstance(val, (int, float))]


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


def and_(a: bool | None, b: bool | None) -> bool | None:
    """conjunction, true if both RHS and LHS are true."""
    return a and b


def or_(a: bool | None, b: bool | None) -> bool | None:
    """disjunction, true if either RHS or LHS is true."""
    return a or b


def in_(a: Any, b: Any) -> bool | None:
    """Object lookup, true if RHS is a subfield of LHS."""
    return operator.contains(b, a) if b is not None else None


def allequal_(array1: list | None, array2: list | None) -> bool:
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


def count_(array: list, val: Any) -> int:
    """Count the number of times a value is found in an array.

    Parameters
    ----------
    array : list
        Array of elements
    val : Any
        value to count

    Returns
    -------
    int
        Number of elements in an array equal to val

    """
    return array.count(val)


def exists_(arg: str | list | None, rule: str | None) -> int:
    """Return a count of files that can be found within the dataset."""
    if arg is None or rule is None:
        return 0

    # Need the actual function here


def index_(arg: str | list | None, val: Any | None) -> int | None:
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


def intersects_(a: list | None, b: list | None) -> list | bool:
    """Find the common values in two arrays.

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

    res = list(set(a) & set(b))

    if res:
        return res
    else:
        return False


def length_(arg: list | None) -> int | None:
    """Find the number of elements in an array.

    Parameters
    ----------
    arg : list | None
        An Array

    Returns
    -------
    int | None
        Number of elements in the array

    """
    if arg is not None:
        return len(arg)


def match_(arg: str | None, pattern: str | None) -> bool | None:
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
        true if arg matches the regular expression pattern (anywhere in string)

    """
    if arg is None:
        return None
    elif pattern is None:
        return False

    res = re.match(pattern, arg)
    return res is not None


def max_(arg: int | float | list | None) -> int | float | None:
    """Find the largest numerical value in an array.

    Parameters
    ----------
    arg : list | None
        The array to evaluate

    Returns
    -------
    int | float | None
        The largest non-n/a value in an array

    """
    if arg is None:
        return None

    if isinstance(arg, (float, int)):
        return arg

    return max(filter_strs(arg))


def min_(arg: int | float | list | None) -> int | float | None:
    """Find the smallest numerical value in an array.

    Parameters
    ----------
    arg : list | None
        The array to evaluate

    Returns
    -------
    int | float | None
        The smallest non-n/a value in an array

    """
    if arg is None:
        return None

    if isinstance(arg, (float, int)):
        return arg

    return min(filter_strs(arg))


def sorted_(arg: list, method: str | None = None) -> list:
    """Return sorted input array.

    Defaults to type-determined sort.
    If method is “lexical”, or “numeric” use lexical or numeric sort.

    Parameters
    ----------
    arg : list
        Array to sort
    method : str | None, optional
        Method to sort by, can be "lexical" or "numerical", by default None

    Returns
    -------
    list
        The sorted values of the input array

    """
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
            sorted_vals = sorted_(numeric_vals, method='numeric')

            for key, val in non_numeric_vals.items():
                sorted_vals.insert(key, val)

            return sorted_vals
        else:
            return sorted(arg, key=int)


def substr_(arg: str | None, start: int | None, end: int | None) -> str | None:
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
        return arg[start:end]


def type_(var: Any) -> str:
    """Evaluate the type of a variable.

    Parameters
    ----------
    var : Any
        Variable to evaluate

    Returns
    -------
    str
        The name of the type, including "array", "object", "null"

    """
    match var:
        case bool():
            return 'boolean'
        case int() | float():
            return 'number'
        case list():
            return 'array'
        case dict():
            return 'object'
        case _:
            return 'null'


def unique_(arg: list | None) -> list | None:
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


def binop(expr: bst_expr.BinOp) -> Any:
    """Evaluate a Binary operation.

    Parameters
    ----------
    expr : bst_expr.BinOp
        Binary operatoion expression

    Returns
    -------
    Any
        Result of operation

    """
    lh = evaluate_arg(expr.lh)
    rh = evaluate_arg(expr.rh)
    func = bin_ops.get(expr.op)
    if func is not None:
        return func(lh, rh)


def rightop(expr: bst_expr.RightOp) -> Any:
    """Evaluate a Right operation.

    Parameters
    ----------
    expr : bst_expr.RightOp
        Right operation expression

    Returns
    -------
    Any
        Result of operation

    """
    rh = evaluate_arg(expr.rh)
    func = right_ops.get(expr.op)
    if func is not None:
        return func(rh)


def array(expr: bst_expr.Array) -> list:
    """Evaluate an Array literal expression.

    Parameters
    ----------
    expr : bst_expr.Array
        Array expression

    Returns
    -------
    list
        An array literal

    """
    return [evaluate_expr(el) for el in expr.elements]


def object_(expr: bst_expr.Object) -> dict:
    """Evaluate an Object literal expression.

    Parameters
    ----------
    expr : bst_expr.Object
        Object expression

    Returns
    -------
    dict
        An Object literal

    """
    return {}


def element(expr: bst_expr.Element) -> Any:
    """Evaluate an Array element lookup.

    Parameters
    ----------
    expr : bst_expr.Element
        Element expression

    Returns
    -------
    Any
        Result of the array lookup

    """
    if isinstance(expr.name, str):
        name = evaluate_arg(expr.name)
        if name is not None:
            return name[expr.index]
        else:
            return None
    elif isinstance(expr.name, bst_expr.Array):
        return expr.name.elements[expr.index]


def function_(expr: bst_expr.Function) -> Any:
    """Evaluate a Function call.

    Parameters
    ----------
    expr : bst_expr.Function
        Function expression

    Returns
    -------
    Any
        Result of the Function call

    Raises
    ------
    ValueError
        If the function is not implemented

    """
    func = functions.get(expr.name)
    args_list = [evaluate_expr(arg) for arg in expr.args]
    if func is not None:
        return func(*args_list)
    else:
        raise ValueError(f'{expr.name} function not available')


def property_(expr: bst_expr.Property) -> Any:
    """Evaluate an Object property lookup expression.

    Parameters
    ----------
    expr : bst_expr.Property
        Property expression

    Returns
    -------
    Any
        Result of the property lookup

    """
    if expr.name in globals():
        return getattr(eval(expr.name), expr.field, None) # noqa: S307


# Available Binary operations
bin_ops = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '/': operator.truediv,
    '%': operator.mod,
    '||': or_,
    '&&': and_,
    '==': operator.eq,
    '!=': operator.ne,
    'in': in_,
}

# Available Right operations
right_ops = {'!': operator.not_}

# Available functions
functions = {
    'allequal': allequal_,
    'count': count_,
    'exists': exists_,
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

# Available expression class types
options = {
    bst_expr.BinOp: binop,
    bst_expr.RightOp: rightop,
    bst_expr.Array: array,
    bst_expr.Element: element,
    bst_expr.Function: function_,
    bst_expr.Property: property_,
    bst_expr.Object: object_,
}


def evaluate_expr(expr):
    """Evaluate an expression.

    Raises
    ------
    ValueError
        If the operation is not implemented

    """
    if isinstance(expr, bst_expr.ASTNode):
        eval_func = options.get(type(expr))
        if eval_func is not None:
            return eval_func(expr)
        else:
            raise ValueError(f'{type(expr)} operation not available.')

    res = evaluate_arg(expr)

    return res
