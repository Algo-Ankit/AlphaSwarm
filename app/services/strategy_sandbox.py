"""
RestrictedPython sandbox — compile and load AI-generated BaseStrategy subclasses safely.

Strategy code receives ONLY these pre-injected symbols (no imports needed or allowed):
  BaseStrategy, OrderIntent, OrderSide, OrderType, Decimal, Optional, math, datetime

pd and np are intentionally excluded — strategies must use self.indicators and
self.close / self.bars property accessors, not raw pandas/numpy computation.
"""
from __future__ import annotations

import ast
import inspect
import operator
from abc import ABCMeta
from decimal import Decimal
from typing import Type

from RestrictedPython import compile_restricted, safe_builtins, safe_globals
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr

from app.domain.base_strategy import BaseStrategy
from app.domain.models import OrderIntent, OrderSide, OrderType


class SandboxError(Exception):
    """Strategy code failed sandbox validation."""


_ALLOWED_IMPORTS = frozenset({"math", "datetime"})


import types as _types


def _write_guard(ob):
    """
    Gate attribute/item writes. Returning `ob` permits the write; raising forbids it.

    Strategies legitimately need instance writes (`self.x = val`) and container
    writes, so those pass. But the sandbox injects *process-shared* singletons —
    the real `math`/`datetime` modules and type objects — and returning them
    unguarded let a strategy do `math.pi = 3`, polluting global state for every
    other strategy in the worker. Writes to modules and type objects are refused.
    """
    if isinstance(ob, (_types.ModuleType, type)):
        raise SandboxError(
            "writing attributes on modules or type objects is forbidden in strategy code"
        )
    return ob


# ── Guarded attribute builtins ───────────────────────────────────────────────
# RestrictedPython routes attribute *syntax* (obj.attr) through safer_getattr,
# which blocks dunders. But the builtin functions getattr/setattr/hasattr bypass
# that guard, so exposing the real ones is a sandbox escape:
#   getattr(getattr((), "__class__"), "__bases__")[0]  →  object
#   getattr(object, "__subclasses__")()                →  every class incl. Popen
# These wrappers reject underscore-prefixed names, matching safer_getattr's policy
# so the builtins cannot be used to reach dunders the syntax path already blocks.
_NO_DEFAULT = object()

# str.format / str.format_map resolve attributes via CPython's format machinery,
# completely outside the sandbox's _getattr_ guard ("{0.__globals__}".format(fn)),
# so they're a graph-traversal escape. safer_getattr blocks them on the syntax
# path; we mirror that denylist here for the builtin getattr path.
_BLOCKED_ATTR_NAMES = frozenset({"format", "format_map"})


def _is_blocked_attr(name) -> bool:
    # Enforce `type(name) is str`: a str *subclass* can override startswith() to
    # return False and smuggle "__class__" past the guard, so anything that is not
    # exactly the built-in str is rejected outright (treated as blocked).
    if type(name) is not str:
        return True
    return name.startswith("_") or name in _BLOCKED_ATTR_NAMES


def _guarded_getattr(obj, name, default=_NO_DEFAULT):
    if _is_blocked_attr(name):
        raise AttributeError(f"access to attribute '{name}' is blocked in strategy code")
    if default is _NO_DEFAULT:
        return getattr(obj, name)
    return getattr(obj, name, default)


def _guarded_setattr(obj, name, value):
    if _is_blocked_attr(name):
        raise AttributeError(f"setting attribute '{name}' is blocked in strategy code")
    return setattr(obj, name, value)


def _guarded_hasattr(obj, name):
    if _is_blocked_attr(name):
        return False
    return hasattr(obj, name)


def _inplacevar(op: str, x, y):
    """Support augmented assignment operators (+=, -= etc.) in strategy code."""
    _ops = {
        "+=":  operator.iadd,
        "-=":  operator.isub,
        "*=":  operator.imul,
        "/=":  operator.itruediv,
        "//=": operator.ifloordiv,
        "%=":  operator.imod,
        "**=": operator.ipow,
    }
    fn = _ops.get(op)
    if fn is None:
        raise TypeError(f"Unsupported in-place operator in strategy code: {op}")
    return fn(x, y)


def _fix_indentation(source: str) -> str:
    """
    Normalize over-indented strategy code.

    textwrap.dedent only helps when ALL non-empty lines share a common indent.
    If comment lines sit at column 0 followed by an indented class definition,
    textwrap.dedent does nothing. This function finds the BaseStrategy subclass
    line and strips its indentation level from every line in the source.
    """
    import textwrap
    source = textwrap.dedent(source)
    lines = source.splitlines()
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue  # skip blanks and comments when measuring class indent
        if stripped.startswith('class ') and 'BaseStrategy' in stripped:
            indent = len(line) - len(stripped)
            if indent > 0:
                prefix = ' ' * indent
                lines = [ln[indent:] if ln.startswith(prefix) else ln for ln in lines]
            break
    return '\n'.join(lines)


_AUG_OPS = [
    ("+=", "+"), ("-=", "-"), ("*=", "*"), ("/=", "/"),
    ("//=", "//"), ("%=", "%"), ("**=", "**"),
]

# Matches:  <indent>self.attr  <aug_op>  <expr>  <optional comment>
_AUG_RE = __import__("re").compile(
    r'^(?P<indent>\s*)(?P<attr>self\.\w+)\s*'
    r'(?P<op>\*\*=|//=|\+=|-=|\*=|/=|%=)\s*'
    r'(?P<expr>.+?)(?P<comment>\s*(?:#.*)?)$'
)


def _auto_correct(source: str) -> str:
    """
    Apply safe mechanical corrections before sandbox validation.

    Fixes:
    1. Attribute augmented assignment  self.x += n  →  self.x = self.x + n
       (RestrictedPython forbids AugAssign on Attribute targets.)
    2. Union return-type hints  -> X | None:  →  -> Optional[X]:
       (The | operator on types is fine at runtime on Python 3.10+ but fails
       inside the RestrictedPython AST transformer on some versions.)
    """
    import re

    lines = source.split('\n')
    out = []
    for line in lines:
        m = _AUG_RE.match(line)
        if m:
            op_map = dict(_AUG_OPS)
            bin_op = op_map.get(m.group('op'))
            if bin_op:
                line = (
                    f"{m.group('indent')}{m.group('attr')} = "
                    f"{m.group('attr')} {bin_op} {m.group('expr')}"
                    f"{m.group('comment')}"
                )
        out.append(line)
    source = '\n'.join(out)

    # -> SomeType | None:  →  -> Optional[SomeType]:
    source = re.sub(
        r'(->)\s*([\w][\w\[\], .]*?)\s*\|\s*None\s*(:)',
        r'\1 Optional[\2]\3',
        source,
    )
    # -> None | SomeType:  →  -> Optional[SomeType]:
    source = re.sub(
        r'(->)\s*None\s*\|\s*([\w][\w\[\], .]*?)\s*(:)',
        r'\1 Optional[\2]\3',
        source,
    )
    return source


def normalize_strategy_code(source: str) -> str:
    """
    Apply all mechanical normalizations (indentation + auto-corrections) and
    return the cleaned source without compiling. Call this before storing code
    so what gets saved is exactly what the sandbox will later execute.
    """
    return _auto_correct(_fix_indentation(source))


def compile_strategy_code(source: str) -> Type[BaseStrategy]:
    """
    Compile source code and return the concrete BaseStrategy subclass.
    Raises SandboxError if code is unsafe, invalid, or has no strategy class.
    """
    source = normalize_strategy_code(source)
    _ast_prescan(source)

    try:
        bytecode = compile_restricted(source, filename="<strategy>", mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"Syntax error in generated strategy: {exc}") from exc

    restricted_builtins = dict(safe_builtins)
    # safe_builtins omits several essential builtins (max, min, sum, list, etc.)
    # that strategy code needs. Add them explicitly — none expose dangerous capabilities.
    restricted_builtins.update({
        "max": max, "min": min, "sum": sum,
        "list": list, "dict": dict, "set": set, "frozenset": frozenset,
        "enumerate": enumerate, "map": map, "filter": filter, "reversed": reversed,
        "any": any, "all": all, "print": print,
        # Dunder-guarded — the real getattr/setattr/hasattr are a sandbox escape.
        "getattr": _guarded_getattr, "hasattr": _guarded_hasattr, "setattr": _guarded_setattr,
        "abs": abs, "round": round, "len": len, "range": range,
        "int": int, "float": float, "str": str, "bool": bool,
        # NOTE: iter/next are deliberately NOT exposed. The 2-arg form
        # `iter(int, 1)` is an infinite loop the AST prescan can't catch
        # (int() never reaches the sentinel). for-loops over real iterables
        # still work via the internal `_getiter_` protocol below.
    })
    restricted_builtins["__import__"] = _blocked_import

    glb: dict = {
        **safe_globals,
        "__builtins__": restricted_builtins,
        # RestrictedPython 8.x injects metaclass=__metaclass__ into every class def.
        # Must be ABCMeta (not type) — BaseStrategy uses ABCMeta; type would conflict.
        "__metaclass__": ABCMeta,
        # class bodies do LOAD_NAME('__name__') to set cls.__module__
        "__name__": "<strategy>",
        "object": object,
        "_getattr_": safer_getattr,
        "_getitem_": operator.getitem,
        "_getiter_": iter,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_write_": _write_guard,
        "_inplacevar_": _inplacevar,
        "BaseStrategy": BaseStrategy,
        "OrderIntent": OrderIntent,
        "OrderSide": OrderSide,
        "OrderType": OrderType,
        "Decimal": Decimal,
        "Optional": __import__("typing").Optional,
        "math": __import__("math"),
        "datetime": __import__("datetime"),
    }
    loc: dict = {}

    try:
        exec(bytecode, glb, loc)  # noqa: S102 — RestrictedPython-compiled bytecode is safe to exec
    except SandboxError:
        raise
    except Exception as exc:
        raise SandboxError(f"Strategy code raised error at load time: {exc}") from exc

    candidates = [
        v for v in {**glb, **loc}.values()
        if isinstance(v, type)
        and issubclass(v, BaseStrategy)
        and v is not BaseStrategy
        and not inspect.isabstract(v)
    ]
    if not candidates:
        raise SandboxError(
            "No concrete BaseStrategy subclass found. "
            "Generated code must define a class extending BaseStrategy with on_bar() implemented."
        )
    return candidates[0]


def _blocked_import(name: str, *args, **kwargs):
    if name in _ALLOWED_IMPORTS:
        return __import__(name, *args, **kwargs)
    raise SandboxError(
        f"Import of '{name}' is not allowed in strategy code. "
        "All needed symbols are pre-injected: BaseStrategy, OrderIntent, "
        "OrderSide, OrderType, Decimal, Optional, math, datetime. "
        "Use self.indicators for indicator values and self.close / self.bars for price data."
    )


def _ast_prescan(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return  # compile_restricted gives the user-facing error
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    raise SandboxError(f"Forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[0] not in _ALLOWED_IMPORTS:
                raise SandboxError(f"Forbidden import: {mod}")
        elif isinstance(node, ast.While):
            raise SandboxError("'while' loops are forbidden to prevent infinite loops.")
