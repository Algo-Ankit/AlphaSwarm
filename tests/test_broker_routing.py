"""
Broker routing + currency tests.
Runnable with pytest OR directly:  python tests/test_broker_routing.py
"""
from decimal import Decimal
from types import SimpleNamespace

from app.domain.broker_routing import (
    broker_for_exchange,
    currency_for_exchange,
    currency_symbol,
)
from app.domain.models import OrderIntent, OrderSide, StrategyRiskConfig
from app.domain.risk import verify_order_intent
from app.services.execution import AlpacaExecutor, UpstoxExecutor, get_executor

_SETTINGS = SimpleNamespace(default_max_order_notional=Decimal("100000000"))


def test_exchange_to_broker():
    assert broker_for_exchange("NASDAQ") == "alpaca"
    assert broker_for_exchange("NYSE") == "alpaca"
    assert broker_for_exchange("CRYPTO") == "alpaca"
    assert broker_for_exchange("NSE") == "upstox"
    assert broker_for_exchange("BSE") == "upstox"
    assert broker_for_exchange("nse") == "upstox"          # case-insensitive
    assert broker_for_exchange("UNKNOWN") == "alpaca"      # safe default


def test_exchange_to_currency():
    assert currency_for_exchange("NASDAQ") == "USD"
    assert currency_for_exchange("NSE") == "INR"
    assert currency_for_exchange("BSE") == "INR"
    assert currency_symbol("USD") == "$"
    assert currency_symbol("INR") == "₹"
    assert currency_symbol("AUD") == "AUD "  # graceful fallback


def test_factory_returns_upstox():
    # Upstox is now a live OAuth executor — it needs an access token. If the
    # upstox SDK isn't installed in this env, the ImportError still proves the
    # factory routed "upstox" → UpstoxExecutor.
    try:
        u = get_executor("upstox", api_key="", secret_key="", paper=False, access_token="tok")
        assert isinstance(u, UpstoxExecutor)
    except (ImportError, ModuleNotFoundError):
        pass


def test_factory_routes_alpaca():
    # AlpacaExecutor.__init__ imports the alpaca SDK; if it isn't installed in this
    # env, the ImportError still proves the factory routed "alpaca" → AlpacaExecutor.
    try:
        a = get_executor("alpaca", api_key="k", secret_key="s", paper=True)
        assert isinstance(a, AlpacaExecutor)
    except (ImportError, ModuleNotFoundError):
        pass


def test_factory_rejects_unknown_broker():
    try:
        get_executor("etrade", api_key="k", secret_key="s")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unsupported broker" in str(exc)


def test_upstox_without_access_token_fails_loudly():
    # Live Upstox requires an OAuth access token; routing without one must fail
    # loudly rather than silently building a broken executor.
    try:
        get_executor("upstox", api_key="k", secret_key="s", paper=False, access_token=None)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "access token" in str(exc).lower()


def test_inr_strategy_rejection_message_uses_rupee_symbol():
    risk = StrategyRiskConfig(allowed_symbols=["RELIANCE"], currency="INR",
                              max_order_notional=Decimal("1000"))
    order = OrderIntent(
        strategy_id="00000000-0000-0000-0000-000000000001",
        symbol="RELIANCE", exchange="NSE", side=OrderSide.buy,
        quantity=Decimal("100"), estimated_price=Decimal("100"), is_paper=True,  # 10_000 > 1_000
    )
    res = verify_order_intent(order, risk, settings=_SETTINGS)
    assert not res.approved
    assert "₹" in res.reason and "$" not in res.reason


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
