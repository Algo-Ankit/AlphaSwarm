"""
Strict-BYOK founder gate tests.

The platform LLM key is a paid/shared resource. Only the founder account
(FOUNDER_EMAIL) may fall back to it; every other account must bring its own key.
These tests lock that policy + the timing-safe, default-deny email match.
Runnable with pytest OR directly:  python tests/test_byok_founder_gate.py
"""
import asyncio
import os

os.environ.setdefault("BROKER_KEY_ENCRYPTION_SECRET", "x" * 40)

from app.domain.models import StrategyCreateRequest  # noqa: E402
from app.services.strategy_compiler import (  # noqa: E402
    _STRICT_BYOK_MESSAGE,
    _is_founder,
    compile_strategy_prompt,
)


def test_is_founder_matches_case_and_space_insensitive():
    assert _is_founder("ankitanandat@gmail.com", "ankitanandat@gmail.com")
    assert _is_founder("  Ankitanandat@GMAIL.com ", "ankitanandat@gmail.com")


def test_is_founder_default_deny():
    # Wrong email, unset founder, and blanks all grant NO exemption.
    assert not _is_founder("attacker@evil.com", "ankitanandat@gmail.com")
    assert not _is_founder("ankitanandat@gmail.com", "")   # FOUNDER_EMAIL unset → locked
    assert not _is_founder(None, "ankitanandat@gmail.com")
    assert not _is_founder("", "ankitanandat@gmail.com")


def test_non_founder_blocked_with_strict_message():
    # Default FOUNDER_EMAIL is empty → every account is non-founder → strict error,
    # raised BEFORE any LLM call (no network needed).
    req = StrategyCreateRequest(name="My Strategy", prompt="buy when rsi below 30", symbols=["SPY"])
    try:
        asyncio.run(compile_strategy_prompt(req, pool=None, user_email="learner@example.com"))
    except ValueError as exc:
        assert str(exc) == _STRICT_BYOK_MESSAGE
        return
    raise AssertionError("expected strict-BYOK ValueError for a non-founder")


def test_founder_uses_platform_fallback(monkeypatch):
    from app.core import config as cfg
    from app.services import strategy_builder as sb

    class _S:
        founder_email = "founder@x.com"
        llm_api_key = "platform-key"
        llm_base_url = "http://local/v1"
        llm_model = "m"

    monkeypatch.setattr(cfg, "get_settings", lambda: _S())

    async def fake_build(**kw):
        # Founder must receive the PLATFORM key, not be rejected.
        assert kw["api_key"] == "platform-key"
        return "class S(BaseStrategy):\n    def on_bar(self):\n        return None"

    async def fake_explain(**kw):
        return "explanation"

    monkeypatch.setattr(sb, "build_strategy_async", fake_build)
    monkeypatch.setattr(sb, "explain_strategy_async", fake_explain)

    req = StrategyCreateRequest(name="Founder Strat", prompt="buy low sell high signals", symbols=["SPY"])
    code, expl = asyncio.run(compile_strategy_prompt(req, pool=None, user_email="founder@x.com"))
    assert "BaseStrategy" in code and expl == "explanation"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            if "monkeypatch" in fn.__code__.co_varnames:
                continue  # needs pytest fixture; skip in direct mode
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed (monkeypatch tests run under pytest)")
