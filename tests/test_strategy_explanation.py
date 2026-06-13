"""
Plain-English strategy explanation tests — pure helpers only (no AutoGen / network).
Runnable with pytest OR directly:  python tests/test_strategy_explanation.py
"""
from app.services.strategy_builder import (
    _build_explain_message,
    _fallback_explanation,
)


def test_fallback_echoes_prompt():
    out = _fallback_explanation("Buy when RSI < 30 and sell when RSI > 70")
    assert "RSI < 30" in out
    assert "RSI > 70" in out
    # Code-free fallback: must not contain Python syntax.
    assert "class " not in out and "def " not in out


def test_fallback_collapses_whitespace():
    out = _fallback_explanation("  buy   low\n\n  sell   high ")
    assert "buy low sell high" in out


def test_fallback_handles_blank_prompt():
    out = _fallback_explanation("   \n  ")
    assert out == "Automated strategy generated from your description."


def test_explain_message_includes_prompt_and_code():
    msg = _build_explain_message("momentum on SPY", "class M(BaseStrategy):\n    pass")
    assert "momentum on SPY" in msg
    assert "class M(BaseStrategy)" in msg
    # The agent is told not to echo the code back.
    assert "do not echo it" in msg.lower()


if __name__ == "__main__":
    import traceback
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
