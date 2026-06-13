"""
Risk engine tests — verify_order_intent is the safety wall ("RISK IS SACRED").

These lock in the Phase 5 risk fixes (short-selling caps #5, directional-flip
turnover #6) and the paper-trading market-hours behaviour (#3). Runnable with
pytest OR directly:  python tests/test_risk.py
"""
from decimal import Decimal
from types import SimpleNamespace

from app.domain.market_data import MarketState
from app.domain.models import OrderIntent, OrderSide, StrategyRiskConfig
from app.domain.risk import verify_order_intent

# Stub settings so tests don't need a real .env / Settings singleton.
_SETTINGS = SimpleNamespace(default_max_order_notional=Decimal("100000000"))


def _order(side: OrderSide, qty: str, price: str = "100", symbol: str = "SPY",
           exchange: str = "NASDAQ") -> OrderIntent:
    return OrderIntent(
        strategy_id="00000000-0000-0000-0000-000000000001",
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=Decimal(qty),
        estimated_price=Decimal(price),
        is_paper=True,
    )


def test_buy_within_limits_is_approved():
    risk = StrategyRiskConfig(allowed_symbols=["SPY"])
    res = verify_order_intent(_order(OrderSide.buy, "5"), risk, settings=_SETTINGS)
    assert res.approved, res.reason


def test_disallowed_symbol_rejected():
    risk = StrategyRiskConfig(allowed_symbols=["SPY"])
    res = verify_order_intent(_order(OrderSide.buy, "1", symbol="TSLA"), risk, settings=_SETTINGS)
    assert not res.approved and "allowed symbols" in res.reason


def test_order_notional_over_limit_rejected():
    risk = StrategyRiskConfig(allowed_symbols=["SPY"], max_order_notional=Decimal("1000"))
    res = verify_order_intent(_order(OrderSide.buy, "100", "100"), risk, settings=_SETTINGS)  # 10_000 > 1_000
    assert not res.approved and "exceeds strategy limit" in res.reason


# ── #5: short selling must respect position caps (was buy-only) ──────────────
def test_short_open_respects_max_position_notional():
    risk = StrategyRiskConfig(
        allowed_symbols=["SPY"],
        max_order_notional=Decimal("1000000"),     # don't trip Check 4
        max_position_notional=Decimal("5000"),
    )
    # Sell 100 @ 100 = 10_000 notional short from flat → exceeds 5_000 position cap.
    res = verify_order_intent(
        _order(OrderSide.sell, "100", "100"), risk,
        settings=_SETTINGS, current_position=0.0, current_position_value=0.0,
    )
    assert not res.approved and "position limit" in res.reason


def test_short_open_respects_max_open_positions():
    risk = StrategyRiskConfig(
        allowed_symbols=["SPY"],
        max_order_notional=Decimal("1000000"),
        max_open_positions=1,
    )
    res = verify_order_intent(
        _order(OrderSide.sell, "1", "100"), risk,
        settings=_SETTINGS, current_position=0.0, current_position_value=0.0,
        open_positions_count=1,
    )
    assert not res.approved and "open positions" in res.reason


# ── #6: directional flip must not exempt the whole order from the daily cap ──
def test_oversized_flip_does_not_bypass_daily_cap():
    risk = StrategyRiskConfig(
        allowed_symbols=["SPY"],
        max_order_notional=Decimal("100000000"),
        max_position_notional=Decimal("100000000"),
        max_daily_notional=Decimal("50000"),
    )
    market = MarketState(exchange="NASDAQ", is_open=True, session_status="open",
                         today_executed_notional=Decimal("0"))
    # Hold 1 share long, sell 10_000 @ 100. Only 1 share is risk-reducing;
    # the other 9_999 open a short and must count toward the 50_000 daily cap.
    res = verify_order_intent(
        _order(OrderSide.sell, "10000", "100"), risk, market,
        settings=_SETTINGS, current_position=1.0, current_position_value=100.0,
    )
    assert not res.approved and "daily limit" in res.reason


def test_genuine_close_is_exempt_from_daily_cap():
    risk = StrategyRiskConfig(
        allowed_symbols=["SPY"],
        max_order_notional=Decimal("100000000"),
        max_position_notional=Decimal("100000000"),
        max_daily_notional=Decimal("50000"),
    )
    market = MarketState(exchange="NASDAQ", is_open=True, session_status="open",
                         today_executed_notional=Decimal("49000"))
    # Closing exactly the 1000-share long adds no new exposure → not blocked by the cap.
    res = verify_order_intent(
        _order(OrderSide.sell, "1000", "100"), risk, market,
        settings=_SETTINGS, current_position=1000.0, current_position_value=100000.0,
    )
    assert res.approved, res.reason


# ── #3 / market hours ───────────────────────────────────────────────────────
def test_market_closed_rejects_when_state_given():
    risk = StrategyRiskConfig(allowed_symbols=["SPY"])
    market = MarketState(exchange="NASDAQ", is_open=False, session_status="closed")
    res = verify_order_intent(_order(OrderSide.buy, "1"), risk, market, settings=_SETTINGS)
    assert not res.approved and "Market is" in res.reason


def test_none_market_state_skips_hours_check():
    """Paper/backtest path passes market_state=None → no hours gate."""
    risk = StrategyRiskConfig(allowed_symbols=["SPY"])
    res = verify_order_intent(_order(OrderSide.buy, "1"), risk, None, settings=_SETTINGS)
    assert res.approved, res.reason


# ── FX-aware platform cap: USD cap vs INR-denominated order ──────────────────
# settings.default_max_order_notional is in USD. An INR order must be compared
# against the cap *converted to INR* (₹83/$ static rate), not the raw USD number.
_USD_CAP = SimpleNamespace(default_max_order_notional=Decimal("1000"))  # $1,000 → ₹83,000


def test_inr_order_over_converted_platform_cap_rejected():
    risk = StrategyRiskConfig(
        allowed_symbols=["RELIANCE"],
        currency="INR",
        max_order_notional=Decimal("100000000"),   # don't trip Check 4
        max_position_notional=Decimal("100000000"),
    )
    # 900 @ ₹100 = ₹90,000 > ₹83,000 converted cap → rejected, message in ₹.
    res = verify_order_intent(
        _order(OrderSide.buy, "900", "100", symbol="RELIANCE", exchange="NSE"),
        risk, settings=_USD_CAP,
    )
    assert not res.approved and "platform-level cap" in res.reason
    assert "₹83000.00" in res.reason and "₹" in res.reason
    assert "$" not in res.reason


def test_inr_order_under_converted_platform_cap_approved():
    risk = StrategyRiskConfig(
        allowed_symbols=["RELIANCE"],
        currency="INR",
        max_order_notional=Decimal("100000000"),
        max_position_notional=Decimal("100000000"),
    )
    # 500 @ ₹100 = ₹50,000 < ₹83,000 converted cap → passes.
    res = verify_order_intent(
        _order(OrderSide.buy, "500", "100", symbol="RELIANCE", exchange="NSE"),
        risk, settings=_USD_CAP,
    )
    assert res.approved, res.reason


def test_usd_order_platform_cap_unchanged():
    risk = StrategyRiskConfig(
        allowed_symbols=["SPY"],
        currency="USD",
        max_order_notional=Decimal("100000000"),
        max_position_notional=Decimal("100000000"),
    )
    # $1,100 > $1,000 cap, no conversion → rejected with $ message.
    res = verify_order_intent(_order(OrderSide.buy, "11", "100"), risk, settings=_USD_CAP)
    assert not res.approved and "platform-level cap" in res.reason
    assert "$1000.00" in res.reason


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
