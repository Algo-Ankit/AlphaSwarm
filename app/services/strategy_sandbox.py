"""
RestrictedPython sandbox — compile and load AI-generated BaseStrategy subclasses safely.

Strategy code receives ONLY these pre-injected symbols (no imports needed or allowed):
  BaseStrategy, OrderIntent, OrderSide, OrderType, Decimal, Optional

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


_FORBIDDEN_TOPS = frozenset({
    "os", "sys", "subprocess", "socket", "urllib", "http",
    "requests", "httpx", "asyncio", "threading", "multiprocessing",
    "pickle", "shelve", "shutil", "pathlib", "io", "tempfile",
    "ftplib", "smtplib", "ctypes", "cffi", "gc",
})


def compile_strategy_code(source: str) -> Type[BaseStrategy]:
    """
    Compile source code and return the concrete BaseStrategy subclass.
    Raises SandboxError if code is unsafe, invalid, or has no strategy class.
    """
    _ast_prescan(source)

    try:
        bytecode = compile_restricted(source, filename="<strategy>", mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"Syntax error in generated strategy: {exc}") from exc

    restricted_builtins = dict(safe_builtins)
    restricted_builtins["__import__"] = _blocked_import

    glb: dict = {
        **safe_globals,
        "__builtins__": restricted_builtins,
        # RestrictedPython 8.x injects metaclass=__metaclass__ into every class def.
        # Must be ABCMeta (not type) — BaseStrategy uses ABCMeta; type would conflict.
        "__metaclass__": ABCMeta,
        # class bodies do LOAD_NAME('__name__') to set cls.__module__
        "__name__": "<strategy>",
        "object": object,  # needed for explicit class X(object) patterns
        "_getattr_": safer_getattr,
        "_getitem_": operator.getitem,
        "_getiter_": iter,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "BaseStrategy": BaseStrategy,
        "OrderIntent": OrderIntent,
        "OrderSide": OrderSide,
        "OrderType": OrderType,
        "Decimal": Decimal,
        "Optional": __import__("typing").Optional,
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
    raise SandboxError(
        f"Import of '{name}' is not allowed in strategy code. "
        "All needed symbols are pre-injected: BaseStrategy, OrderIntent, "
        "OrderSide, OrderType, Decimal, Optional. "
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
                if alias.name.split(".")[0] in _FORBIDDEN_TOPS:
                    raise SandboxError(f"Forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[0] in _FORBIDDEN_TOPS:
                raise SandboxError(f"Forbidden import: {mod}")
