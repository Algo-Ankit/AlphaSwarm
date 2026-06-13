"""
BacktestRunner — industry-standard bar-by-bar simulation.

Design invariants:
  - Cash/position tracked separately; equity = cash + position × close (mark-to-market)
  - Signal generated on bar[i]; filled at bar[i+1].open (no lookahead bias)
  - Risk evaluated at signal-time estimated_price (no lookahead); fill executed at bar[i+1].open
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
# pandas_ta is imported lazily inside _precompute_indicators so the pure-math
# parts of this module (e.g. _compute_metrics) can be imported/tested without it.

from app.domain.base_strategy import BaseStrategy, ReadOnlyDataFrame, StrategyContext
from app.domain.market_data import Bar, MarketState
from app.domain.models import OrderIntent, OrderSide, OrderType, StrategyRiskConfig
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
class BacktestBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


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
    # Extended risk-adjusted + benchmark metrics (additive; default 0.0 keeps old callers safe)
    sortino_ratio: float = 0.0
    cagr_pct: float = 0.0
    calmar_ratio: float = 0.0
    profit_factor: float = 0.0
    benchmark_return_pct: float = 0.0
    alpha_vs_benchmark_pct: float = 0.0


@dataclass
class BacktestResult:
    strategy_id: str
    symbol: str
    timeframe: str
    bars_processed: int
    bars: list[BacktestBar]
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
    last_date = None
    today_notional = 0.0

    # Execution-cost params (hoisted so both entry fills and bracket exits use them)
    slippage_bps = float(rc.get("slippage_bps", 5.0))
    commission_per_share = float(rc.get("commission_per_share", 0.005))

    # Broker-enforced bracket exit levels for the currently open position.
    # Set only on a clean entry from flat (non-crypto) — mirrors the live worker.
    exit_stop_price: float | None = None
    exit_take_price: float | None = None

    strategy_instance = None

    for i in range(len(bars)):
        close_price = float(bars[i].close)
        if math.isnan(close_price):
            continue

        # 0. Broker-enforced bracket exits (stop-loss / take-profit). The live worker
        #    attaches these legs to the entry order; here we trigger them intrabar
        #    against this bar's high/low BEFORE any new signal so paper matches live.
        if position != 0:
            exit_fill = _bracket_exit_fill(
                position, exit_stop_price, exit_take_price,
                float(bars[i].high), float(bars[i].low), slippage_bps,
            )
            if exit_fill is not None:
                exit_side, exit_px = exit_fill
                qty = abs(position)
                fill_price = Decimal(str(exit_px))
                commission = commission_per_share * float(qty)
                notional = float(qty) * float(fill_price)
                if exit_side == OrderSide.sell:   # close long
                    cash += (notional - commission)
                else:                             # cover short
                    cash -= (notional + commission)
                trades.append(BacktestTrade(
                    bar_index=i,
                    timestamp=bars[i].timestamp,
                    symbol=symbol,
                    side=exit_side.value,
                    quantity=qty,
                    price=fill_price,
                ))
                position = Decimal("0")
                avg_cost = None
                exit_stop_price = None
                exit_take_price = None

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
        ctx_bars = ReadOnlyDataFrame(full_df.iloc[window_start : i + 1])

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

        if strategy_instance is None:
            strategy_instance = strategy_class(ctx)
        else:
            strategy_instance.ctx = ctx

        # 5. Strategy signal evaluated on bar i's state
        signal: OrderIntent | None = strategy_instance.on_bar()
        if signal is None:
            continue

        # 6. Fill price = NEXT bar's open — eliminates lookahead bias
        next_open_val = float(bars[i + 1].open)
        if math.isnan(next_open_val):
            continue
        next_open = Decimal(str(next_open_val))

        current_pos = float(position) if position else None

        current_date = bars[i].timestamp.date()
        if last_date != current_date:
            today_notional = 0.0
            last_date = current_date

        mock_state = MarketState(
            exchange=exchange,
            is_open=True,
            session_status="open",
            today_executed_notional=Decimal(str(today_notional)),
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
        commission = commission_per_share * float(qty)
        prev_pos = position

        if signal.order_type == OrderType.limit and signal.limit_price is not None:
            if signal.side == OrderSide.buy and float(bars[i + 1].low) > float(signal.limit_price):
                continue
            if signal.side == OrderSide.sell and float(bars[i + 1].high) < float(signal.limit_price):
                continue
            base_fill = signal.limit_price
        else:
            base_fill = next_open

        if signal.side == OrderSide.buy:
            fill_price = base_fill * Decimal(str(1 + slippage_bps / 10000.0))
        else:
            fill_price = base_fill * Decimal(str(1 - slippage_bps / 10000.0))
            
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

        # Maintain bracket exit levels, mirroring the live worker: attach legs only on a
        # clean entry from flat (non-crypto); a flip or full close cancels them; a same-side
        # add keeps the original legs.
        flat_entry = prev_pos == 0
        flipped = (prev_pos > 0 and position < 0) or (prev_pos < 0 and position > 0)
        if position == 0:
            exit_stop_price = exit_take_price = None
        elif flat_entry and exchange.upper() != "CRYPTO" and (
            risk_profile.stop_loss_pct is not None or risk_profile.take_profit_pct is not None
        ):
            exit_stop_price, exit_take_price = _bracket_exit_levels(
                position > 0, float(signal.estimated_price),
                risk_profile.stop_loss_pct, risk_profile.take_profit_pct,
            )
        elif flipped:
            exit_stop_price = exit_take_price = None

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
    metrics = _compute_metrics(equity_curve, trades, initial_equity, final_equity, timeframe, bars)

    bar_records = [
        BacktestBar(
            timestamp=b.timestamp,
            open=float(b.open),
            high=float(b.high),
            low=float(b.low),
            close=float(b.close),
            volume=b.volume,
        )
        for b in bars
    ]

    return BacktestResult(
        strategy_id=strategy_id,
        symbol=symbol,
        timeframe=timeframe,
        bars_processed=len(bars),
        bars=bar_records,
        trades=trades,
        equity_curve=equity_curve,
        metrics=metrics,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bracket_exit_levels(
    is_long: bool,
    ref_price: float,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> tuple[float | None, float | None]:
    """
    Compute (stop_loss_price, take_profit_price) for a bracket attached on entry.
    Mirrors the live worker (app/worker/tasks.py): for a long, the stop sits below
    and the take above the reference price; inverted for a short.
    """
    stop = take = None
    if is_long:
        if stop_loss_pct is not None:
            stop = ref_price * (1 - stop_loss_pct / 100.0)
        if take_profit_pct is not None:
            take = ref_price * (1 + take_profit_pct / 100.0)
    else:
        if stop_loss_pct is not None:
            stop = ref_price * (1 + stop_loss_pct / 100.0)
        if take_profit_pct is not None:
            take = ref_price * (1 - take_profit_pct / 100.0)
    return stop, take


def _bracket_exit_fill(
    position: Decimal,
    stop_price: float | None,
    take_price: float | None,
    bar_high: float,
    bar_low: float,
    slippage_bps: float,
) -> tuple[OrderSide, float] | None:
    """
    If this bar's range touches a stop/take leg, return (exit_side, fill_price); else None.

    Conventions matching the live bracket model:
      - Pessimistic: if both legs are touched in one bar, the stop fills first.
      - Stop legs convert to market orders → adverse slippage applied.
      - Take legs are limit orders → fill at the exact limit price (no slippage).
    """
    if position == 0:
        return None
    slip = slippage_bps / 10000.0
    if position > 0:  # long: stop below entry, take above
        stop_hit = stop_price is not None and not math.isnan(bar_low) and bar_low <= stop_price
        take_hit = take_price is not None and not math.isnan(bar_high) and bar_high >= take_price
        if stop_hit:
            return OrderSide.sell, stop_price * (1 - slip)
        if take_hit:
            return OrderSide.sell, take_price
    else:             # short: stop above entry, take below
        stop_hit = stop_price is not None and not math.isnan(bar_high) and bar_high >= stop_price
        take_hit = take_price is not None and not math.isnan(bar_low) and bar_low <= take_price
        if stop_hit:
            return OrderSide.buy, stop_price * (1 + slip)
        if take_hit:
            return OrderSide.buy, take_price
    return None


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
    import pandas_ta as ta

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
    bars: list[Bar] | None = None,
) -> BacktestMetrics:
    import numpy as np

    total_return_pct = (
        (final_equity - initial_equity) / initial_equity * 100.0
        if initial_equity else 0.0
    )

    # Timeframe-correct Sharpe annualization
    bars_per_year = _BARS_PER_YEAR.get(timeframe, _BARS_PER_YEAR.get(timeframe.lower(), 252.0))
    ann_factor = math.sqrt(bars_per_year)

    sharpe = 0.0
    sortino = 0.0
    if len(equity_curve) > 1:
        eq = np.array(equity_curve, dtype=np.float64)
        denom = np.where(eq[:-1] != 0, eq[:-1], 1.0)
        returns = np.diff(eq) / denom
        if len(returns) > 1:
            std = float(returns.std(ddof=1))
            sharpe = float(returns.mean() / std * ann_factor) if std > 0 else 0.0
            # Sortino: penalise only downside volatility (returns below 0).
            downside = returns[returns < 0]
            dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
            sortino = float(returns.mean() / dstd * ann_factor) if dstd > 0 else 0.0

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

    # Simple Win Rate + gross P&L: Track Realized P&L on closing trades
    profitable = 0
    closing_trades = 0
    gross_profit = 0.0   # sum of positive realised P&L (for profit factor)
    gross_loss = 0.0     # sum of |negative realised P&L|
    sim_pos = Decimal("0")
    sim_avg_cost = 0.0
    for t in trades:
        qty = t.quantity
        if t.side == "buy":
            if sim_pos < 0:
                closing_trades += 1
                closed_qty = min(float(qty), float(abs(sim_pos)))
                pnl = (sim_avg_cost - float(t.price)) * closed_qty  # short: profit when price falls
                if pnl >= 0:
                    profitable += 1
                    gross_profit += pnl
                else:
                    gross_loss += -pnl
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
                closed_qty = min(float(qty), float(sim_pos))
                pnl = (float(t.price) - sim_avg_cost) * closed_qty  # long: profit when price rises
                if pnl >= 0:
                    profitable += 1
                    gross_profit += pnl
                else:
                    gross_loss += -pnl
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

    # Profit factor: gross win / gross loss. 999.0 sentinel = profits with zero losing trades.
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = 999.0 if gross_profit > 0 else 0.0

    # ── CAGR, Calmar, and buy-and-hold benchmark ─────────────────────────────
    # Reality check: a strategy that can't beat passively holding the asset isn't alpha.
    years = 0.0
    benchmark_return_pct = 0.0
    if bars:
        span_days = (bars[-1].timestamp - bars[0].timestamp).total_seconds() / 86400.0
        years = span_days / 365.25 if span_days > 0 else 0.0
        first_close = float(bars[0].close)
        last_close = float(bars[-1].close)
        if first_close > 0:
            benchmark_return_pct = (last_close - first_close) / first_close * 100.0
    if years <= 0:
        years = len(equity_curve) / bars_per_year if bars_per_year else 0.0

    if years > 0 and initial_equity > 0 and final_equity > 0:
        cagr_pct = ((final_equity / initial_equity) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr_pct = total_return_pct

    calmar = (cagr_pct / max_dd) if max_dd > 0 else 0.0
    alpha_vs_benchmark_pct = total_return_pct - benchmark_return_pct

    return BacktestMetrics(
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 3),
        sortino_ratio=round(sortino, 3),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 1),
        total_trades=len(trades),
        profitable_trades=profitable,
        initial_equity=round(initial_equity, 2),
        final_equity=final_equity,
        cagr_pct=round(cagr_pct, 2),
        calmar_ratio=round(calmar, 3),
        profit_factor=round(profit_factor, 3),
        benchmark_return_pct=round(benchmark_return_pct, 2),
        alpha_vs_benchmark_pct=round(alpha_vs_benchmark_pct, 2),
    )
