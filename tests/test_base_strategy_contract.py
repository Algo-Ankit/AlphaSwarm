"""
BaseStrategy contract guard.

A strategy gets its strategy_id from the StrategyContext (self.ctx.strategy_id),
NOT from the frozen risk config (self.ctx.risk has no strategy_id field). The
docstring example and the AutoGen system prompt are the templates humans and the
LLM copy, so a wrong field there silently propagates into every generated/hand-
written strategy and crashes OrderIntent construction at the first order. These
tests lock the correct contract.

Runnable with pytest OR directly:  python tests/test_base_strategy_contract.py
"""
import inspect

from app.domain.base_strategy import BaseStrategy, StrategyContext
from app.domain.models import StrategyRiskConfig


def test_strategy_id_lives_on_context_not_risk():
    assert "strategy_id" in StrategyContext.__dataclass_fields__
    # StrategyRiskConfig (self.ctx.risk) must NOT carry strategy_id.
    assert "strategy_id" not in StrategyRiskConfig.model_fields
    rp = StrategyRiskConfig(allowed_symbols=["TEST"])
    try:
        _ = rp.strategy_id
    except AttributeError:
        return
    raise AssertionError("StrategyRiskConfig unexpectedly exposes strategy_id")


def test_docstring_example_uses_ctx_strategy_id():
    doc = BaseStrategy.__doc__ or ""
    assert "self.ctx.strategy_id" in doc, "docstring example must show the correct field"
    assert "self.ctx.risk.strategy_id" not in doc, (
        "docstring still references self.ctx.risk.strategy_id — that field does not exist"
    )


def test_system_prompt_uses_ctx_strategy_id():
    # The AutoGen builder's template must also use the correct field.
    from app.services import strategy_builder
    src = inspect.getsource(strategy_builder)
    assert "self.ctx.risk.strategy_id" not in src


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
