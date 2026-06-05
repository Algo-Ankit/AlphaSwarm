"""
BacktestRunner — industry-standard bar-by-bar simulation.

Design invariants:
  - Cash/position tracked separately; equity = cash + position × close (mark-to-market)
  - Signal generated on bar[i]; filled at bar[i+1].open (no lookahead bias)
  - estimated_price hard-overridden to actual fill before verify_order_intent
  - Indicators precomputed O(n) on full dataset; strategy receives a bounded VIEW (no copy)
  - Bankruptcy halts the simulation immediately
  - Sharpe annualization factor derived from timeframe, not hardcoded to sqrt(252)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
import pandas_ta as ta

from app.domain.base_strategy import BaseStrategy, StrategyContext
from app.domain.market_data import Bar
from app.domain.models import OrderIntent, OrderSide, StrategyRiskConfig
from app.domain.risk import verify_order_intent
from app.services.strategy_sandbox import SandboxError, compile_strategy_code

logger = logging.getLogger(__name__)

# Max historical bars passed to StrategyContext — bounds the view size to O(1) per bar
_CONTEXT_WINDOW = 300

# Trading-period annualization factor per timeframe
_BARS_PER_YEAR: dict[str, float] = {
    "1m":   252 * 390,
    "1min": 252 * 390,
    "5m":   252 * 78,
    "5min": 252 * 78,
    "15m":  252 * 26,
    "15min": 252 * 26,
    "1h":   252 * 6.5,
    "4h":   252 * 1.625,
    "1d":   252.0,
    "1D":   252.0,
    "1w":   52.0,
    "1W":   52.0,
}


@dataclass
class BacktestTrade:
    bar_index: int       # index of the signal bar (fill is at bar_index+1 open)
    timestamp: datetime  # close timestamp of the signal bar
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal       # actual fill price = bars[bar_index+1].open


@dataclass
class BacktestMetrics:
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    profitable_trades: int
    initial_equity: float
    final_equity: float


@dataclass
class BacktestResult:
    strategy_id: str
    symbol: str
    timeframe: str
    bars_processed: int
    trades: list[BacktestTrade]
    equity_curve: list[float]
    metrics: BacktestMetrics
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_backtest(
    strategy_id: str,
    source_code: str,
    bars: list[Bar],
    timeframe: str,
    risk_config: dict,
    initial_equity: float = 10_000.0,
) -> BacktestResult:
    """
    Execute source_code strategy on historical bars. Returns BacktestResult.
    Raises SandboxError for unsafe code; ValueError for insufficient data.
    """
    started_at = datetime.now(timezone.utc)

    if len(bars) < 2:
        raise ValueError("Backtest requires at least 2 bars.")

    strategy_class = compile_strategy_code(source_code)

    symbol = bars[0].symbol
    exchange = bars[0].exchange

    # Guarantee the tested symbol passes Check 3 in verify_order_intent
    rc = dict(risk_config)
    allowed = {s.upper() for s in rc.get("allowed_symbols", [])}
    allowed.add(symbol.upper())
    rc["allowed_symbols"] = list(allowed)
    risk_profile = StrategyRiskConfig.model_validate(rc)

    # ── Precompute indicators on full dataset — O(n) ──────────────────────────
    full_df = _bars_to_df(bars)
    indicator_rows = _precompute_indicators(full_df)

    # ── Simulation state ──────────────────────────────────────────────────────
    cash: float = float(initial_equity)
    position: Decimal = Decimal("0")
    avg_cost: float | None = None
    equity_curve: list[float] = []
    trades: list[BacktestTrade] = []

    for i in range(len(bars)):
        close_price = float(bars[i].close)

        # 1. Mark-to-market at close of bar i
        equity = cash + float(position) * close_price
        equity_curve.append(round(equity, 2))

        # 2. Bankruptcy check — halt if equity wiped out
        if equity <= 0.0:
            logger.warning(
                "Backtest halted at bar %d: equity=%.2f (bankruptcy)", i, equity
            )
            if position != 0:
                cash += float(position) * close_price
                position = Decimal("0")
            break

        # 3. Cannot fill after the last bar — stop signalling
        if i == len(bars) - 1:
            break

        # 4. Build bounded context view — wrapped safely
        window_start = max(0, i + 1 - _CONTEXT_WINDOW)
        ctx_bars_raw = full_df.iloc[window_start : i + 1]
        
        from app.domain.base_strategy import ReadOnlyDataFrame
        ctx_bars = ReadOnlyDataFrame(ctx_bars_raw)

        ctx = StrategyContext(
            strategy_id=strategy_id,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            bars=ctx_bars,
            indicators=indicator_rows[i],
            position=float(position) if position else None,
            avg_cost=avg_cost,
            risk=risk_profile,
        )

        # 5. Strategy signal evaluated on bar i's state
        signal: OrderIntent | None = strategy_class(ctx).on_bar()
        if signal is None:
            continue

        # 6. Fill price = NEXT bar's open — eliminates lookahead bias
        next_open = Decimal(str(float(bars[i + 1].open)))

        # 7. Hard-override estimated_price so risk engine sees the true fill price
        signal = signal.model_copy(update={"estimated_price": next_open})

        current_pos = float(position) if position else None

        # Track simulated daily notional for Risk Check 5 (resets each new calendar day)
        from app.domain.market_data import MarketState
        current_date = bars[i].timestamp.date()
        if 'last_date' not in locals() or last_date != current_date:  # type: ignore[name-defined]
            today_notional = 0.0
            last_date = current_date

        mock_state = MarketState(
            symbol=symbol,
            exchange=exchange,
            timestamp=bars[i].timestamp,
            is_open=True,
            session_status="open",
            price=close_price,
            today_executed_notional=Decimal(str(today_notional))
        )

        risk_result = verify_order_intent(
            signal, risk_profile, market_state=mock_state, current_position=current_pos
        )
        if not risk_result.approved:
            logger.debug("Bar %d: risk rejected — %s", i, risk_result.reason)
            continue

        # Gross turnover: every approved order consumes the daily cap regardless of side.
        today_notional += float(risk_result.order_notional)

        # 8. Execute fill with slippage and commission
        qty = signal.quantity
        slippage_bps = float(rc.get("slippage_bps", 5.0))
        commission = float(rc.get("commission_per_trade", 0.0))

        if signal.side == OrderSide.buy:
            fill_price = next_open * Decimal(str(1 + slippage_bps / 10000.0))
        else:
            fill_price = next_open * Decimal(str(1 - slippage_bps / 10000.0))
            
        notional = float(qty * fill_price)

        if signal.side == OrderSide.buy:
            cash -= (notional + commission)
            if position >= 0:
                new_qty = position + qty
                avg_cost = float((Decimal(str(avg_cost or 0)) * position + fill_price * qty) / new_qty)
                position = new_qty
            else:
                new_qty = position + qty
                if new_qty > 0:
                    avg_cost = float(fill_price)
                elif new_qty == 0:
                    avg_cost = None
                position = new_qty
        else:
            cash += (notional - commission)
            if position <= 0:
                new_qty = position - qty
                avg_cost = float((Decimal(str(avg_cost or 0)) * abs(position) + fill_price * qty) / abs(new_qty))
                position = new_qty
            else:
                new_qty = position - qty
                if new_qty < 0:
                    avg_cost = float(fill_price)
                elif new_qty == 0:
                    avg_cost = None
                position = new_qty

        trades.append(BacktestTrade(
            bar_index=i,
            timestamp=bars[i].timestamp,
            symbol=symbol,
            side=signal.side.value,
            quantity=qty,
            price=fill_price,
        ))

    # ── Liquidate any remaining open position at last available close ─────────
    # Formula: cash += position × last_close handles both long (+ cash) and short (- cash)
    if position != 0:
        cash += float(position) * float(bars[-1].close)

    final_equity = round(cash, 2)
    metrics = _compute_metrics(equity_curve, trades, initial_equity, final_equity, timeframe)

    return BacktestResult(
        strategy_id=strategy_id,
        symbol=symbol,
        timeframe=timeframe,
        bars_processed=len(bars),
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bars_to_df(bars: list[Bar]) -> pd.DataFrame:
    df = pd.DataFrame({
        "open":   [float(b.open)   for b in bars],
        "high":   [float(b.high)   for b in bars],
        "low":    [float(b.low)    for b in bars],
        "close":  [float(b.close)  for b in bars],
        "volume": [float(b.volume) for b in bars],
    })
    df.index = pd.DatetimeIndex([b.timestamp for b in bars])
    return df


def _precompute_indicators(df: pd.DataFrame) -> list[dict]:
    """Compute full indicator time series once; return one dict per bar."""
    n = len(df)
    rows: list[dict] = [{} for _ in range(n)]

    def _fill(series, key: str) -> None:
        if series is None:
            return
        for idx, val in enumerate(series):
            if pd.notna(val):
                rows[idx][key] = float(val)

    def _fill_frame(frame) -> None:
        if frame is None or (hasattr(frame, "empty") and frame.empty):
            return
        for col in frame.columns:
            _fill(frame[col], col)

    _fill(ta.rsi(df["close"], length=14), "RSI_14")
    _fill_frame(ta.macd(df["close"], fast=12, slow=26, signal=9))
    _fill(ta.ema(df["close"], length=20), "EMA_20")
    _fill(ta.ema(df["close"], length=50), "EMA_50")
    _fill(ta.ema(df["close"], length=200), "EMA_200")
    _fill_frame(ta.bbands(df["close"], length=20, std=2.0))
    _fill(ta.atr(df["high"], df["low"], df["close"], length=14), "ATRr_14")

    return rows


def _compute_metrics(
    equity_curve: list[float],
    trades: list[BacktestTrade],
    initial_equity: float,
    final_equity: float,
    timeframe: str,
) -> BacktestMetrics:
    import numpy as np

    total_return_pct = (
        (final_equity - initial_equity) / initial_equity * 100.0
        if initial_equity else 0.0
    )

    # Timeframe-correct Sharpe annualization
    bars_per_year = _BARS_PER_YEAR.get(timeframe, _BARS_PER_YEAR.get(timeframe.lower(), 252.0))
    ann_factor = math.sqrt(bars_per_year)

    if len(equity_curve) > 1:
        eq = np.array(equity_curve, dtype=np.float64)
        denom = np.where(eq[:-1] != 0, eq[:-1], 1.0)
        returns = np.diff(eq) / denom
        # BUG FIX #8: was dividing returns.mean() (all bars) by active_returns.std()
        # (bars with trades only) — mixing populations produces impossible Sharpe values.
        # Both mean and std must use the same population.
        if len(returns) > 1:
            std = float(returns.std(ddof=1))
            sharpe = float(returns.mean() / std * ann_factor) if std > 0 else 0.0
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # Max drawdown (peak-to-trough on equity curve)
    peak = initial_equity
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    # Simple Win Rate: Track Realized P&L on closing trades
    profitable = 0
    closing_trades = 0
    sim_pos = Decimal("0")
    sim_avg_cost = 0.0
    for t in trades:
        qty = t.quantity
        if t.side == "buy":
            if sim_pos < 0:
                closing_trades += 1
                if t.price < sim_avg_cost:
                    profitable += 1
                sim_pos += qty
                if sim_pos > 0:
                    sim_avg_cost = float(t.price)
                elif sim_pos == 0:
                    sim_avg_cost = 0.0
            else:
                new_pos = sim_pos + qty
                sim_avg_cost = float((Decimal(str(sim_avg_cost)) * sim_pos + t.price * qty) / new_pos)
                sim_pos = new_pos
        else:
            if sim_pos > 0:
                closing_trades += 1
                if t.price > sim_avg_cost:
                    profitable += 1
                sim_pos -= qty
                if sim_pos < 0:
                    sim_avg_cost = float(t.price)
                elif sim_pos == 0:
                    sim_avg_cost = 0.0
            else:
                new_pos = sim_pos - qty
                sim_avg_cost = float((Decimal(str(sim_avg_cost)) * abs(sim_pos) + t.price * qty) / abs(new_pos))
                sim_pos = new_pos

    win_rate = (profitable / closing_trades * 100.0) if closing_trades > 0 else 0.0

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 1),
        total_trades=len(trades),
        profitable_trades=profitable,
        initial_equity=round(initial_equity, 2),
        final_equity=final_equity,
    )
