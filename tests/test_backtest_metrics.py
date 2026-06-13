"""
Backtest metrics tests — extended risk-adjusted + benchmark metrics.
Runnable with pytest OR directly:  python tests/test_backtest_metrics.py
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.market_data import Bar
from app.domain.models import OrderSide
from app.services.backtest import (
    BacktestTrade,
    _bracket_exit_fill,
    _bracket_exit_levels,
    _compute_metrics,
)


def _bars(closes: list[float]) -> list[Bar]:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for i, c in enumerate(closes):
        out.append(Bar(
            symbol="SPY", exchange="NASDAQ", timeframe="1d",
            timestamp=t0 + timedelta(days=i),
            open=Decimal(str(c)), high=Decimal(str(c)), low=Decimal(str(c)),
            close=Decimal(str(c)), volume=1000,
        ))
    return out


def _trade(side: str, qty: str, price: str, idx: int) -> BacktestTrade:
    return BacktestTrade(
        bar_index=idx, timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol="SPY", side=side, quantity=Decimal(qty), price=Decimal(price),
    )


def test_benchmark_and_alpha():
    # Asset rises 100 → 110 = +10% buy-and-hold. Strategy made +5%.
    bars = _bars([100, 105, 110])
    m = _compute_metrics([10000, 10200, 10500], [], 10000.0, 10500.0, "1d", bars)
    assert m.benchmark_return_pct == 10.0
    assert m.total_return_pct == 5.0
    assert m.alpha_vs_benchmark_pct == -5.0  # underperformed the benchmark


def test_profit_factor_one_win_one_loss():
    # Buy 1@100, sell 1@110 (+10 profit); buy 1@100, sell 1@90 (-10 loss). PF = 1.0
    trades = [
        _trade("buy", "1", "100", 0),
        _trade("sell", "1", "110", 1),
        _trade("buy", "1", "100", 2),
        _trade("sell", "1", "90", 3),
    ]
    m = _compute_metrics([10000, 10010, 10010, 10000], trades, 10000.0, 10000.0, "1d", _bars([100, 110, 100, 90]))
    assert m.total_trades == 4
    assert m.profitable_trades == 1
    assert m.profit_factor == 1.0


def test_profit_factor_no_losses_sentinel():
    trades = [_trade("buy", "1", "100", 0), _trade("sell", "1", "110", 1)]
    m = _compute_metrics([10000, 10010], trades, 10000.0, 10010.0, "1d", _bars([100, 110]))
    assert m.profit_factor == 999.0  # profits with zero losing trades


def test_sortino_present_and_finite():
    bars = _bars([100, 101, 99, 102, 98, 103])
    m = _compute_metrics([10000, 10100, 9900, 10200, 9800, 10300], [], 10000.0, 10300.0, "1d", bars)
    assert isinstance(m.sortino_ratio, float)
    assert m.cagr_pct != 0.0  # span > 0 so CAGR computed


def test_bracket_levels_long_and_short():
    # Long entry @100, SL 2% / TP 5% → stop below, take above.
    stop, take = _bracket_exit_levels(True, 100.0, 2.0, 5.0)
    assert stop == 98.0 and take == 105.0
    # Short entry @100 → inverted: stop above, take below.
    stop, take = _bracket_exit_levels(False, 100.0, 2.0, 5.0)
    assert stop == 102.0 and take == 95.0
    # Disabled legs stay None.
    assert _bracket_exit_levels(True, 100.0, None, None) == (None, None)


def test_bracket_exit_long_stop_take_and_none():
    # Long position, stop=98, take=105, no slippage.
    # Bar dips to 97 → stop fires, sell at stop (adverse slippage applied).
    res = _bracket_exit_fill(Decimal("1"), 98.0, 105.0, bar_high=99.0, bar_low=97.0, slippage_bps=10.0)
    assert res is not None and res[0] == OrderSide.sell
    assert abs(res[1] - 98.0 * (1 - 0.001)) < 1e-9
    # Bar rallies to 106 (low stays above stop) → take fires at exact limit, no slippage.
    res = _bracket_exit_fill(Decimal("1"), 98.0, 105.0, bar_high=106.0, bar_low=99.0, slippage_bps=10.0)
    assert res == (OrderSide.sell, 105.0)
    # Quiet bar inside both legs → no exit.
    assert _bracket_exit_fill(Decimal("1"), 98.0, 105.0, bar_high=104.0, bar_low=99.0, slippage_bps=10.0) is None


def test_bracket_exit_both_hit_stop_wins_and_short_side():
    # Long: bar straddles both legs → pessimistic stop fills first.
    res = _bracket_exit_fill(Decimal("1"), 98.0, 105.0, bar_high=106.0, bar_low=97.0, slippage_bps=0.0)
    assert res == (OrderSide.sell, 98.0)
    # Short position (negative qty): stop above (102), take below (95).
    # Bar spikes to 103 → stop fires, BUY to cover with adverse slippage.
    res = _bracket_exit_fill(Decimal("-1"), 102.0, 95.0, bar_high=103.0, bar_low=99.0, slippage_bps=10.0)
    assert res is not None and res[0] == OrderSide.buy
    assert abs(res[1] - 102.0 * (1 + 0.001)) < 1e-9
    # Short bar drops to 94 → take fires, BUY to cover at exact limit.
    res = _bracket_exit_fill(Decimal("-1"), 102.0, 95.0, bar_high=100.0, bar_low=94.0, slippage_bps=10.0)
    assert res == (OrderSide.buy, 95.0)


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
