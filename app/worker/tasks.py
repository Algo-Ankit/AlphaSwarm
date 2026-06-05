"""
Phase 4 execution engine — real on_bar() loop with Alpaca order placement.
Default strategy: RSI(14) momentum. Phase 5 replaces with AutoGen-generated code.
"""
import asyncio
import logging
from decimal import Decimal
from uuid import UUID

import pandas as pd

from app.core.celery_app import celery_app
from app.domain.base_strategy import BaseStrategy, StrategyContext
from app.domain.market_data import MarketState
from app.domain.models import (
    OrderIntent, OrderResult, OrderSide, OrderType, StrategyRiskConfig,
)
from app.domain.risk import verify_order_intent
from app.worker.run_logger import RunLogger

logger = logging.getLogger(__name__)


# ── Default strategy (fallback until Phase 5 generates code) ─────────────────

class _DefaultRSIStrategy(BaseStrategy):
    """RSI(14) momentum: BUY when RSI < 30 and flat; SELL when RSI > 70 and long."""

    def on_bar(self) -> OrderIntent | None:
        rsi = self.indicators.get("RSI_14")
        if rsi is None:
            return None

        close = self.close
        max_notional = float(self.ctx.risk.max_order_notional)
        qty = Decimal(str(int(max_notional / close)))
        if qty < 1:
            # Stock price exceeds max_order_notional — let risk engine reject, don't bypass
            return None

        if rsi < 30 and self.is_flat:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id,
                symbol=self.ctx.symbol,
                exchange=self.ctx.exchange,
                side=OrderSide.buy,
                quantity=qty,
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )

        if rsi > 70 and self.is_long:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id,
                symbol=self.ctx.symbol,
                exchange=self.ctx.exchange,
                side=OrderSide.sell,
                quantity=Decimal(str(abs(self.position))),
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )

        return None


# ── DB write helper (uses shared pool — no new pool per order) ────────────────

async def _write_order_async(
    pool,
    tenant_id: str,
    strategy_id: str,
    run_id: str,
    intent: OrderIntent,
    result: OrderResult,
    risk_status: str,
    risk_reason: str,
) -> None:
    side_sign = Decimal("1") if intent.side == OrderSide.buy else Decimal("-1")
    delta = intent.quantity * side_sign
    fill = result.fill_price or intent.estimated_price

    await pool.execute(
        """
        INSERT INTO orders
            (tenant_id, strategy_id, run_id, broker_order_id,
             symbol, exchange, side, order_type,
             quantity, estimated_price, fill_price,
             estimated_notional, risk_status, risk_reason,
             broker_status, filled_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                CASE WHEN $15 = 'filled' THEN now() ELSE NULL END)
        """,
        UUID(tenant_id), UUID(strategy_id),
        UUID(run_id),
        result.order_id,
        intent.symbol, intent.exchange,
        intent.side.value, intent.order_type.value,
        # Pass Decimal directly to asyncpg — avoids float precision loss
        intent.quantity, intent.estimated_price,
        result.fill_price,
        intent.estimated_notional,
        risk_status, risk_reason,
        result.broker_status,
    )

    await pool.execute(
        """
        INSERT INTO positions
            (tenant_id, strategy_id, symbol, exchange, quantity, avg_cost, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (tenant_id, strategy_id, symbol) DO UPDATE
        SET quantity = positions.quantity + $5,
            avg_cost = CASE
                -- Adding to / opening a long (delta > 0, current qty ≥ 0)
                WHEN $5 > 0 AND positions.quantity >= 0 THEN
                    COALESCE(
                        (positions.avg_cost * positions.quantity + $6 * $5) /
                        NULLIF(positions.quantity + $5, 0),
                        0
                    )
                -- Adding to / opening a short (delta < 0, current qty ≤ 0)
                WHEN $5 < 0 AND positions.quantity <= 0 THEN
                    COALESCE(
                        (positions.avg_cost * ABS(positions.quantity) + $6 * ABS($5)) /
                        NULLIF(ABS(positions.quantity) + ABS($5), 0),
                        0
                    )
                -- Flipping from Short to Long
                WHEN $5 > 0 AND positions.quantity < 0 AND positions.quantity + $5 > 0 THEN
                    $6
                -- Flipping from Long to Short
                WHEN $5 < 0 AND positions.quantity > 0 AND positions.quantity + $5 < 0 THEN
                    $6
                -- Closing to exactly zero
                WHEN positions.quantity + $5 = 0 THEN
                    NULL
                -- Partial close in either direction
                ELSE positions.avg_cost
            END,
            updated_at = now()
        """,
        UUID(tenant_id), UUID(strategy_id),
        intent.symbol, intent.exchange,
        delta, fill,
    )


# ── Full async execution body (single pool, single asyncio.run call) ──────────

async def _execute_async(
    strategy_id: str,
    tenant_id: str,
    user_id: str,
    run_id: str | None,
    dry_run: bool,
    symbols: list[str],
    timeframe: str,
    risk_config: dict,
) -> dict:
    import asyncpg

    from app.core.config import get_settings
    from app.db.repositories.brokers import BrokerRepo
    from app.db.repositories.runs import RunRepo
    from app.domain.market_hours import get_session_status
    from app.services.broker_crypto import decrypt_key
    from app.services.indicators import _compute_indicators_sync
    from app.services.market_data import get_bars

    settings = get_settings()
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    pool = None
    log = RunLogger(run_id) if run_id else None

    try:
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)

        tradable_symbols = [s.upper() for s in (symbols or ["SPY"])]
        risk_profile = StrategyRiskConfig.model_validate(
            risk_config or {"allowed_symbols": tradable_symbols}
        )

        if log:
            log.status("running")
            log.info(
                f"Worker started — strategy {strategy_id[:8]}",
                symbols=tradable_symbols,
                dry_run=dry_run,
                mode="paper" if dry_run else "live",
            )
            log.info(
                f"Risk profile — max order ${risk_profile.max_order_notional:.0f}  "
                f"daily ${risk_profile.max_daily_notional:.0f}"
            )

        broker_repo = BrokerRepo(pool, UUID(tenant_id))
        run_repo = RunRepo(pool, UUID(tenant_id))

        if run_id:
            await run_repo.mark_running(UUID(run_id))

        # Load broker connection
        brokers = await broker_repo.get_all()
        broker_row = next((b for b in brokers if b["broker"] == "alpaca"), None)

        if not dry_run and broker_row is None:
            raise RuntimeError(
                "Live trading requested but no active Alpaca broker connection found. "
                "Add credentials in Settings → Broker Connections."
            )

        broker_creds = None
        if broker_row:
            broker_creds = {
                "api_key": decrypt_key(broker_row["key_encrypted"]),
                "secret_key": decrypt_key(broker_row["secret_encrypted"]),
                "paper": bool(broker_row["is_paper"]),
            }

        # Today's notional uses Eastern Time — US market day resets at ET midnight, not UTC
        # Gross Notional Turnover: sum ALL orders (buys + sells) regardless of side.
        # We cannot reconstruct risk-adding vs. risk-reducing without replaying position
        # state, so we treat max_daily_notional as a turnover cap. A $10k cap allows
        # $5k buys + $5k sells — both directions consume the budget equally.
        # This prevents a malicious strategy from shorting to infinity across worker restarts.
        today_notional_row = await pool.fetchrow(
            """
            SELECT COALESCE(SUM(estimated_notional), 0) AS total
            FROM orders
            WHERE tenant_id = $1
              AND strategy_id = $2
              AND broker_status IN ('filled', 'open', 'pending')
              AND created_at >= (
                  date_trunc('day', now() AT TIME ZONE 'America/New_York')
                  AT TIME ZONE 'America/New_York'
              )
            """,
            UUID(tenant_id), UUID(strategy_id),
        )
        today_notional = Decimal(str(today_notional_row["total"])) if today_notional_row else Decimal("0")

        # Fetch bars + compute indicators per symbol
        bars_by_symbol: dict[str, list] = {}
        dfs_by_symbol: dict[str, pd.DataFrame] = {}
        indicators_by_symbol: dict[str, dict] = {}

        for symbol in tradable_symbols:
            bars = await get_bars(
                symbol=symbol, exchange="NASDAQ", timeframe=timeframe, limit=250, pool=pool
            )
            bars_by_symbol[symbol] = bars
            if bars:
                df = pd.DataFrame({
                    "open":   [float(b.open)   for b in bars],
                    "high":   [float(b.high)   for b in bars],
                    "low":    [float(b.low)    for b in bars],
                    "close":  [float(b.close)  for b in bars],
                    "volume": [float(b.volume) for b in bars],
                })
                df.index = pd.DatetimeIndex([b.timestamp for b in bars])
                dfs_by_symbol[symbol] = df
                indicators_by_symbol[symbol] = _compute_indicators_sync(
                    bars, "rsi(14),macd(12,26,9),ema(20),ema(50),ema(200),bb(20,2),atr(14)"
                )
            else:
                dfs_by_symbol[symbol] = pd.DataFrame()
                indicators_by_symbol[symbol] = {}

        # Load DB positions for this strategy only (not the full broker account)
        positions: dict[str, Decimal] = {}
        avg_costs: dict[str, float | None] = {}
        pos_rows = await pool.fetch(
            "SELECT symbol, quantity, avg_cost FROM positions WHERE tenant_id = $1 AND strategy_id = $2",
            UUID(tenant_id), UUID(strategy_id),
        )
        for row in pos_rows:
            sym = row["symbol"].upper()
            positions[sym] = Decimal(str(row["quantity"]))
            avg_costs[sym] = float(row["avg_cost"]) if row["avg_cost"] is not None else None

        # Setup live executor — only refresh positions for tradable symbols to prevent
        # cross-strategy position leakage from other strategies sharing the broker account
        executor = None
        if not dry_run and broker_creds:
            from app.services.execution import AlpacaExecutor
            executor = AlpacaExecutor(
                api_key=broker_creds["api_key"],
                secret_key=broker_creds["secret_key"],
                paper=broker_creds["paper"],
            )
            # BUG FIX #5: Do NOT override DB positions with broker live_positions.
            # Two strategies trading the same symbol would corrupt each other's
            # position state — the broker account is a shared resource.
            # Source of truth for per-strategy positions is the positions table.
            if log:
                log.info(f"Broker connected — paper={broker_creds['paper']}  positions={dict(positions)}")

        results = []

        # Load AI-generated strategy class from DB (Phase 5); fall back to default RSI
        from app.services.strategy_sandbox import SandboxError, compile_strategy_code

        strategy_row = await pool.fetchrow(
            """
            SELECT sv.generated_logic
            FROM strategies s
            JOIN strategy_versions sv ON sv.id = s.current_version_id
            WHERE s.id = $1 AND s.tenant_id = $2
            """,
            UUID(strategy_id), UUID(tenant_id),
        )
        generated_logic = (strategy_row["generated_logic"] or "") if strategy_row else ""

        _strategy_class = None
        if len(generated_logic.strip()) > 30:
            try:
                _strategy_class = compile_strategy_code(generated_logic)
                if log:
                    log.info(f"Loaded AI-generated strategy class: {_strategy_class.__name__}")
            except SandboxError as exc:
                if log:
                    log.info(f"Sandbox load failed ({exc}) — using default RSI strategy")

        for symbol in tradable_symbols:
            bars = bars_by_symbol.get(symbol, [])
            bars_df = dfs_by_symbol.get(symbol, pd.DataFrame())
            ind = indicators_by_symbol.get(symbol, {})

            if len(bars) < 20:
                if log:
                    log.info(f"{symbol}: insufficient bars ({len(bars)}) — skipping")
                continue

            close = float(bars[-1].close)
            position_qty = positions.get(symbol)
            avg_cost = avg_costs.get(symbol)

            if log:
                rsi_val = ind.get("RSI_14")
                rsi_str = f"RSI={rsi_val:.1f}" if rsi_val is not None else "RSI=n/a"
                strat_name = _strategy_class.__name__ if _strategy_class else "_DefaultRSIStrategy"
                log.info(f"{symbol}  close=${close:.2f}  {rsi_str}  position={position_qty}  strategy={strat_name}")

            ctx = StrategyContext(
                strategy_id=strategy_id,
                symbol=symbol,
                exchange="NASDAQ",
                timeframe=timeframe,
                bars=bars_df,
                indicators=ind,
                position=float(position_qty) if position_qty is not None else None,
                avg_cost=avg_cost,
                risk=risk_profile,
            )
            active_class = _strategy_class if _strategy_class is not None else _DefaultRSIStrategy
            try:
                signal: OrderIntent | None = active_class(ctx).on_bar()
            except Exception as exc:
                if log:
                    log.error(f"{symbol}: strategy crashed during on_bar: {exc}")
                results.append({"symbol": symbol, "action": "error", "reason": str(exc)})
                continue

            if signal is None:
                if log:
                    log.info(f"{symbol}: no signal this bar")
                results.append({"symbol": symbol, "action": "hold"})
                continue

            if log:
                log.signal(
                    f"Signal → {signal.side.value.upper()} {symbol}  "
                    f"qty={signal.quantity}  price≈${signal.estimated_price}  "
                    f"notional=${signal.estimated_notional:.2f}",
                    side=signal.side.value, symbol=symbol,
                    quantity=str(signal.quantity),
                    estimated_price=str(signal.estimated_price),
                )

            # Risk check — pass current position so Check 5 can distinguish
            # risk-reducing closes from risk-adding opens/shorts
            session = get_session_status("NASDAQ")
            market_state = MarketState(
                exchange="NASDAQ",
                is_open=session == "open",
                session_status=session,
                today_executed_notional=today_notional,
            )
            current_pos = float(position_qty) if position_qty is not None else None
            current_pos_qty = positions.get(symbol) or Decimal("0")
            current_pos_value = float(abs(current_pos_qty)) * close
            open_pos_count = sum(1 for q in positions.values() if q and q != 0)
            risk_result = verify_order_intent(
                signal, risk_profile, market_state, current_position=current_pos,
                current_position_value=current_pos_value,
                open_positions_count=open_pos_count,
            )

            if not risk_result.approved:
                if log:
                    log.risk(f"REJECTED — {risk_result.reason}")
                results.append({"symbol": symbol, "action": "rejected", "reason": risk_result.reason})
                continue

            if log:
                log.risk(f"PASSED — notional ${risk_result.order_notional:.2f}")

            # Place or paper-log order
            if dry_run:
                order_result = OrderResult(
                    order_id=None,
                    symbol=symbol,
                    side=signal.side,
                    quantity=signal.quantity,
                    fill_price=None,
                    estimated_price=signal.estimated_price,
                    broker_status="dry_run",
                    is_paper=True,
                )
                if log:
                    log.order(
                        f"[DRY RUN] {signal.side.value.upper()} {symbol} × {signal.quantity} "
                        f"@ ~${signal.estimated_price}  (no real order placed)"
                    )
            else:
                order_result = executor.place_order(signal)
                if log:
                    log.order(
                        f"LIVE order: {signal.side.value.upper()} {symbol} × {signal.quantity} "
                        f"— broker_status={order_result.broker_status}  id={order_result.order_id}"
                    )

            # Gross turnover: every approved order consumes the daily cap regardless of
            # whether it opens or closes a position. Consistent with the SQL startup sum.
            today_notional += risk_result.order_notional

            if run_id:
                await _write_order_async(
                    pool, tenant_id, strategy_id, run_id,
                    signal, order_result, "approved", risk_result.reason,
                )

            results.append({
                "symbol": symbol,
                "action": signal.side.value,
                "quantity": str(signal.quantity),
                "estimated_price": str(signal.estimated_price),
                "broker_status": order_result.broker_status,
                "order_id": order_result.order_id,
            })

        final_result = {
            "status": "completed",
            "run_id": run_id,
            "strategy_id": strategy_id,
            "dry_run": dry_run,
            "orders": results,
        }

        if log:
            log.status("completed", f"Run finished — {len(results)} symbol(s) processed")

        if run_id:
            await run_repo.mark_completed(UUID(run_id), final_result)

        return final_result

    except Exception as exc:
        logger.exception("execute_trading_strategy failed: %s", exc)
        if log:
            log.error(f"Worker exception: {exc}")
            log.status("failed", str(exc))
        if run_id and pool is not None:
            try:
                from app.db.repositories.runs import RunRepo as _RunRepo
                await _RunRepo(pool, UUID(tenant_id)).mark_crashed(UUID(run_id), str(exc))
            except Exception:
                pass
        raise

    finally:
        if pool is not None:
            await pool.close()
        if log:
            log.close()


# ── Celery task entry point ───────────────────────────────────────────────────

@celery_app.task(name="app.worker.tasks.execute_trading_strategy")
def execute_trading_strategy(
    strategy_id: str,
    tenant_id: str,
    user_id: str,
    run_id: str | None = None,
    dry_run: bool = True,
    symbols: list[str] | None = None,
    timeframe: str = "1d",
    risk_config: dict | None = None,
):
    # Live orders require a run_id — without it there is no audit trail
    if not dry_run and run_id is None:
        raise ValueError(
            "Cannot execute live orders without run_id — no audit trail would be recorded."
        )

    return asyncio.run(_execute_async(
        strategy_id=strategy_id,
        tenant_id=tenant_id,
        user_id=user_id,
        run_id=run_id,
        dry_run=dry_run,
        symbols=symbols or ["SPY"],
        timeframe=timeframe,
        risk_config=risk_config or {},
    ))
