"""
Sandbox malicious-input tests — RestrictedPython strategy sandbox.

ROADMAP GATE: "RestrictedPython sandbox must be tested with malicious input
before the Phase 6 frontend opens the code editor to users." The Monaco editor
is already live, so this is the gate.

Two defense layers are exercised:
  • COMPILE-time: AST prescan (imports / while) + RestrictedPython transforms
    (dunder attribute syntax, eval, __import__) → SandboxError.
  • RUNTIME: compile_strategy_code does NOT call on_bar(), so escapes hidden in
    on_bar() only trigger when the strategy actually runs. These tests compile
    the strategy AND invoke on_bar() against a minimal context to prove the
    runtime guards hold.

Regression anchor: the real getattr/setattr/hasattr builtins were once exposed,
allowing  getattr(getattr((),"__class__"),"__bases__")[0]  →  object  →
getattr(object,"__subclasses__")()  → subprocess.Popen (full RCE). They are now
dunder-guarded. test_getattr_dunder_escape_blocked locks that shut.

Runnable with pytest OR directly:  python tests/test_sandbox_security.py
"""
import pandas as pd

from app.domain.base_strategy import ReadOnlyDataFrame, StrategyContext
from app.domain.models import StrategyRiskConfig
from app.services.strategy_sandbox import SandboxError, compile_strategy_code

_DF = pd.DataFrame([{"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1} for _ in range(3)])


def _ctx() -> StrategyContext:
    return StrategyContext(
        strategy_id="00000000-0000-0000-0000-000000000001",
        symbol="T", exchange="NASDAQ", timeframe="1d",
        bars=ReadOnlyDataFrame(_DF), indicators={}, position=None, avg_cost=None,
        risk=StrategyRiskConfig(allowed_symbols=["T"]),
    )


def _strategy(on_bar_body: str, module_prefix: str = "") -> str:
    """Wrap a body into a valid BaseStrategy subclass source string."""
    src = (module_prefix + "\n") if module_prefix else ""
    src += "class S(BaseStrategy):\n    def on_bar(self):\n"
    src += "".join("        " + ln + "\n" for ln in on_bar_body.splitlines())
    return src


def _assert_blocked_at_compile(src: str):
    try:
        compile_strategy_code(src)
    except SandboxError:
        return
    raise AssertionError("expected SandboxError at compile time, code compiled")


def _assert_blocked_at_runtime(on_bar_body: str):
    """Compiles, but invoking on_bar() must raise (escape denied)."""
    cls = compile_strategy_code(_strategy(on_bar_body))
    try:
        cls(_ctx()).on_bar()
    except Exception:
        return
    raise AssertionError("expected on_bar() to raise; escape succeeded")


# ── Compile-time: forbidden imports ──────────────────────────────────────────
def test_import_os_blocked():
    _assert_blocked_at_compile(_strategy("return None", module_prefix="import os"))


def test_from_import_blocked():
    _assert_blocked_at_compile(_strategy("return None", module_prefix="from os import system"))


def test_import_subprocess_blocked():
    _assert_blocked_at_compile(_strategy("return None", module_prefix="import subprocess"))


def test_import_sys_blocked():
    _assert_blocked_at_compile(_strategy("return None", module_prefix="import sys"))


def test_import_submodule_blocked():
    _assert_blocked_at_compile(_strategy("return None", module_prefix="import os.path"))


def test_allowed_imports_still_work():
    # math / datetime are explicitly allowed.
    compile_strategy_code(_strategy("return None", module_prefix="import math"))
    compile_strategy_code(_strategy("return None", module_prefix="import datetime"))


# ── Compile-time: control flow + RestrictedPython transforms ─────────────────
def test_while_loop_blocked():
    _assert_blocked_at_compile(_strategy("while True:\n    pass"))


def test_dunder_attribute_syntax_blocked():
    _assert_blocked_at_compile(_strategy("return ().__class__"))


def test_subclasses_syntax_blocked():
    _assert_blocked_at_compile(_strategy("return ().__class__.__bases__[0].__subclasses__()"))


def test_eval_blocked():
    _assert_blocked_at_compile(_strategy('return eval("1+1")'))


def test_dunder_import_call_blocked():
    _assert_blocked_at_compile(_strategy('return __import__("os")'))


# ── Runtime: builtins removed → NameError ────────────────────────────────────
def test_open_blocked_at_runtime():
    _assert_blocked_at_runtime('return open("/etc/passwd").read()')


def test_globals_blocked_at_runtime():
    _assert_blocked_at_runtime("return globals()")


def test_compile_blocked_at_runtime():
    _assert_blocked_at_runtime('return compile("1", "x", "eval")')


# ── Runtime: guarded getattr/setattr/hasattr (the RCE regression) ────────────
def test_getattr_dunder_escape_blocked():
    # The historical full-RCE path. Must raise, not return object/Popen.
    _assert_blocked_at_runtime('return getattr(getattr((), "__class__"), "__bases__")[0]')


def test_getattr_subclasses_chain_blocked():
    _assert_blocked_at_runtime(
        'o = getattr(getattr((), "__class__"), "__bases__")[0]\n'
        'return getattr(o, "__subclasses__")()'
    )


def test_setattr_dunder_blocked():
    _assert_blocked_at_runtime('setattr(self, "__class__", int)\nreturn None')


def test_no_class_in_subclasses_reachable():
    # Belt-and-suspenders: the escape must not be able to enumerate Popen.
    cls = compile_strategy_code(_strategy(
        'try:\n'
        '    o = getattr(getattr((), "__class__"), "__bases__")[0]\n'
        '    subs = getattr(o, "__subclasses__")()\n'
        '    return any(getattr(c, "__name__", "") == "Popen" for c in subs)\n'
        'except Exception:\n'
        '    return "blocked"'
    ))
    assert cls(_ctx()).on_bar() == "blocked"


# ── Legitimate code must still work ──────────────────────────────────────────
def test_guarded_getattr_allows_non_dunder():
    cls = compile_strategy_code(_strategy('return getattr(self, "position", None) is None'))
    assert cls(_ctx()).on_bar() is True


def test_guarded_hasattr_non_dunder_works_dunder_false():
    cls = compile_strategy_code(_strategy('return [hasattr(self, "position"), hasattr((), "__class__")]'))
    assert cls(_ctx()).on_bar() == [True, False]


def test_augmented_assignment_autocorrected():
    # self.x += 1 is auto-rewritten; must compile and run. (_strategy handles indent.)
    cls = compile_strategy_code(_strategy("self.n = 0\nself.n += 1\nreturn None"))
    inst = cls(_ctx())
    assert inst.on_bar() is None


def test_baseline_strategy_runs():
    cls = compile_strategy_code(_strategy("return None"))
    assert cls(_ctx()).on_bar() is None


if __name__ == "__main__":
    import os
    import traceback
    os.environ.setdefault("BROKER_KEY_ENCRYPTION_SECRET", "x" * 40)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    raise SystemExit(0 if passed == len(fns) else 1)
