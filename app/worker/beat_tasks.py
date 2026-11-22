"""
Celery Beat periodic tasks.
snapshot_portfolio and reconcile_positions implemented in Phase 4.
refresh_active_symbols_news and refresh_stale_forecasts implemented here (Phase 3C).
"""

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


def _get_pool():
    """Create a fresh asyncpg pool for use inside a sync Celery task."""
    import asyncpg

    return asyncpg.create_pool(
        _settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1,
        max_size=3,
    )


def _publish_portfolio(tenant_id: str, payload: dict) -> None:
    """Best-effort sync publish to the tenant portfolio channel (Celery-safe)."""
    import json

    from app.core.redis_pool import get_sync_redis

    try:
        # Shared process-wide client — reused across beats, never per-call created/closed.
        get_sync_redis().publish(f"portfolio:{tenant_id}", json.dumps(payload))
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("snapshot_portfolio publish failed for %s: %s", tenant_id, exc)


@celery_app.task(name="app.worker.beat_tasks.snapshot_portfolio")
def snapshot_portfolio():
    """Write a portfolio_snapshots row for every active tenant every 5 minutes."""
    asyncio.run(_snapshot_portfolio_async())


async def _snapshot_portfolio_async() -> None:
    from decimal import Decimal

    pool = await _get_pool()
    try:
        # Get all tenants with at least one active broker connection
        rows = await pool.fetch(
            """
            SELECT DISTINCT bc.tenant_id
            FROM broker_connections bc
            WHERE bc.is_active = true
            """
        )
        if not rows:
            logger.info("snapshot_portfolio: no active broker connections")
            return

        for row in rows:
            tenant_id = row["tenant_id"]
            try:
                # Aggregate open positions
                pnl_row = await pool.fetchrow(
                    """
                    SELECT
                        COUNT(DISTINCT strategy_id) AS active_strategies,
                        COALESCE(SUM(unrealized_pnl), 0) AS open_pnl
                    FROM positions
                    WHERE tenant_id = $1 AND quantity != 0
                    """,
                    tenant_id,
                )
                # Today's realized P&L from orders filled today (or positions updated today)
                realized_row = await pool.fetchrow(
                    """
                    SELECT COALESCE(SUM(realized_pnl), 0) AS realized
                    FROM orders
                    WHERE tenant_id = $1
                      AND filled_at >= date_trunc('day', now())
                      AND risk_status = 'approved'
                    """,
                    tenant_id,
                )
                open_pnl = Decimal(str(pnl_row["open_pnl"] or 0))
                realized_today = Decimal(str(realized_row["realized"] or 0))
                active = int(pnl_row["active_strategies"] or 0)

                # Query broker account equity & cash balance if available
                broker_row = await pool.fetchrow(
                    """
                    SELECT * FROM broker_connections
                    WHERE tenant_id = $1 AND is_active = true
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    tenant_id,
                )
                cash_balance = None
                broker_equity = None
                if broker_row:
                    try:
                        from app.services.broker_crypto import decrypt_key
                        from app.services.execution import get_executor

                        access_token = (
                            decrypt_key(broker_row["access_token"])
                            if broker_row.get("access_token")
                            else None
                        )
                        api_key = (
                            decrypt_key(broker_row["key_encrypted"])
                            if broker_row.get("key_encrypted")
                            else ""
                        )
                        secret_key = (
                            decrypt_key(broker_row["secret_encrypted"])
                            if broker_row.get("secret_encrypted")
                            else ""
                        )
                        executor = get_executor(
                            broker_row["broker"],
                            api_key=api_key,
                            secret_key=secret_key,
                            paper=bool(broker_row["is_paper"]),
                            access_token=access_token,
                        )
                        acct = await asyncio.to_thread(executor.get_account)
                        if acct:
                            if acct.get("cash") is not None:
                                cash_balance = float(acct["cash"])
                            if acct.get("equity") is not None:
                                broker_equity = float(acct["equity"])
                    except Exception as b_exc:
                        logger.debug(
                            "snapshot_portfolio: broker account fetch skipped for tenant %s: %s",
                            tenant_id,
                            b_exc,
                        )

                if broker_equity is not None:
                    total_equity = broker_equity
                elif cash_balance is not None:
                    total_equity = cash_balance + float(open_pnl)
                else:
                    total_equity = float(open_pnl + realized_today)

                snap = await pool.fetchrow(
                    """
                    INSERT INTO portfolio_snapshots
                        (tenant_id, total_equity, cash_balance, open_pnl, realized_pnl_today, active_strategies)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING snapshot_time
                    """,
                    tenant_id,
                    total_equity,
                    cash_balance,
                    float(open_pnl),
                    float(realized_today),
                    active,
                )
                # Live fan-out to /v1/ws/portfolio subscribers for this tenant.
                await asyncio.to_thread(
                    _publish_portfolio,
                    str(tenant_id),
                    {
                        "type": "portfolio",
                        "snapshot_time": snap["snapshot_time"].isoformat(),
                        "total_equity": total_equity,
                        "open_pnl": float(open_pnl),
                        "realized_pnl_today": float(realized_today),
                        "active_strategies": active,
                    },
                )
            except Exception as exc:
                logger.warning("snapshot_portfolio: tenant %s failed: %s", tenant_id, exc)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.refresh_active_symbols_news")
def refresh_active_symbols_news():
    """
    Fetch and cache latest news for all symbols with currently running strategies.
    Runs every hour at :00. Skips symbols that were refreshed within the last hour.
    """
    asyncio.run(_refresh_news_async())


async def _refresh_news_async() -> None:
    from app.db.repositories.intelligence import NewsRepo
    from app.services.news_intel import get_news

    pool = await _get_pool()
    try:
        repo = NewsRepo(pool)
        active = await repo.get_active_symbols()
        if not active:
            logger.info("refresh_active_symbols_news: no running strategies")
            return

        logger.info(
            "refresh_active_symbols_news: refreshing %d symbols: %s",
            len(active),
            active,
        )
        for symbol, exchange in active:
            try:
                items = await get_news(
                    symbol=symbol,
                    exchange=exchange,
                    days=7,
                    limit=20,
                    pool=pool,
                )
                logger.info("  %s (%s): %d news items cached", symbol, exchange, len(items))
            except Exception as exc:
                logger.warning("  %s (%s): news refresh failed: %s", symbol, exchange, exc)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.refresh_stale_forecasts")
def refresh_stale_forecasts():
    """
    Regenerate Prophet+ARIMA forecasts older than 1 hour for all actively-watched symbols.
    Runs every hour at :30.
    """
    asyncio.run(_refresh_forecasts_async())


async def _refresh_forecasts_async() -> None:
    from datetime import datetime, timedelta, timezone

    from app.db.repositories.intelligence import ForecastRepo, NewsRepo
    from app.services.forecaster import get_forecast

    _STALE_THRESHOLD = timedelta(hours=1)

    pool = await _get_pool()
    try:
        news_repo = NewsRepo(pool)
        fc_repo = ForecastRepo(pool)
        active = await news_repo.get_active_symbols()
        if not active:
            logger.info("refresh_stale_forecasts: no running strategies")
            return

        logger.info("refresh_stale_forecasts: checking %d symbols", len(active))
        now = datetime.now(timezone.utc)

        for symbol, exchange in active:
            try:
                cached = await fc_repo.get_latest(symbol, exchange, horizon_days=5)
                if cached:
                    gen_at = cached["generated_at"]
                    if gen_at.tzinfo is None:
                        gen_at = gen_at.replace(tzinfo=timezone.utc)
                    if (now - gen_at) < _STALE_THRESHOLD:
                        logger.info("  %s (%s): forecast fresh, skipping", symbol, exchange)
                        continue

                result = await get_forecast(
                    symbol=symbol,
                    exchange=exchange,
                    horizon_days=5,
                    pool=pool,
                )
                logger.info(
                    "  %s (%s): forecast regenerated (mae=%.4f)",
                    symbol,
                    exchange,
                    result.mae or 0,
                )
            except Exception as exc:
                logger.warning("  %s (%s): forecast refresh failed: %s", symbol, exchange, exc)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.check_worker_heartbeats")
def check_worker_heartbeats():
    """Mark runs stuck in 'running' > 90s with no DB update as failed."""
    asyncio.run(_check_heartbeats_async())


async def _check_heartbeats_async() -> None:
    pool = await _get_pool()
    try:
        # Find all stale running runs across all tenants
        stale = await pool.fetch(
            """
            SELECT id, tenant_id FROM strategy_runs
            WHERE status = 'running'
              AND updated_at < now() - INTERVAL '90 seconds'
            """
        )
        if not stale:
            return

        logger.warning("check_worker_heartbeats: %d stale run(s) found", len(stale))
        for row in stale:
            run_id = row["id"]
            tenant_id = row["tenant_id"]
            await pool.execute(
                """
                UPDATE strategy_runs
                SET status = 'failed',
                    error = 'Worker heartbeat timeout — process likely crashed',
                    ended_at = now(),
                    updated_at = now()
                WHERE id = $1 AND tenant_id = $2
                """,
                run_id,
                tenant_id,
            )
            logger.warning("  marked run %s as failed (heartbeat timeout)", run_id)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.cleanup_refresh_tokens")
def cleanup_refresh_tokens():
    """Purge refresh tokens that expired > 7 days ago (unbounded-growth guard)."""
    asyncio.run(_cleanup_refresh_tokens_async())


async def _cleanup_refresh_tokens_async() -> None:
    pool = await _get_pool()
    try:
        result = await pool.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < now() - INTERVAL '7 days'"
        )
        logger.info("cleanup_refresh_tokens: %s", result)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.reconcile_positions")
def reconcile_positions():
    """End-of-day: compare DB positions against actual broker positions."""
    asyncio.run(_reconcile_positions_async())


async def _reconcile_positions_async() -> None:
    from decimal import Decimal

    pool = await _get_pool()
    try:
        brokers = await pool.fetch("SELECT * FROM broker_connections WHERE is_active = true")
        if not brokers:
            logger.info("reconcile_positions: no active broker connections")
            return

        from app.services.broker_crypto import decrypt_key
        from app.services.execution import get_executor

        for row in brokers:
            tenant_id = row["tenant_id"]
            broker = row["broker"]
            try:
                # Route to the connection's actual broker (alpaca / upstox / …),
                # not a hardcoded Alpaca. Unsupported / not-yet-implemented brokers
                # raise inside get_executor / get_positions and are logged below.
                access_token = (
                    decrypt_key(row["access_token"])
                    if row.get("access_token")
                    else None
                )
                api_key = (
                    decrypt_key(row["key_encrypted"])
                    if row.get("key_encrypted")
                    else ""
                )
                secret_key = (
                    decrypt_key(row["secret_encrypted"])
                    if row.get("secret_encrypted")
                    else ""
                )
                executor = get_executor(
                    broker,
                    api_key=api_key,
                    secret_key=secret_key,
                    paper=bool(row["is_paper"]),
                    access_token=access_token,
                )
                broker_positions = await asyncio.to_thread(executor.get_positions)

                # Load DB positions for this tenant
                db_rows = await pool.fetch(
                    "SELECT symbol, quantity FROM positions WHERE tenant_id = $1",
                    tenant_id,
                )
                db_positions = {r["symbol"].upper(): Decimal(str(r["quantity"])) for r in db_rows}

                for symbol, broker_qty in broker_positions.items():
                    db_qty = db_positions.get(symbol, Decimal("0"))
                    diff = abs(broker_qty - db_qty)
                    if diff > Decimal("0.0001"):
                        # Log discrepancy — cannot auto-correct since strategy_id is required
                        logger.warning(
                            "reconcile_positions: MISMATCH tenant=%s  %s  db=%s  broker=%s  diff=%s",
                            tenant_id,
                            symbol,
                            db_qty,
                            broker_qty,
                            diff,
                        )

                logger.info(
                    "reconcile_positions: tenant=%s  broker=%s  broker_positions=%d  db_positions=%d",
                    tenant_id,
                    broker,
                    len(broker_positions),
                    len(db_positions),
                )
            except Exception as exc:
                logger.warning(
                    "reconcile_positions: tenant %s broker %s failed: %s",
                    tenant_id,
                    broker,
                    exc,
                )
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.recompute_commons_oos")
def recompute_commons_oos():
    """
    Recompute the out-of-sample scorecard for published strategies.

    Anti-survivorship-bias: for each listing we backtest its PINNED immutable
    version over data strictly AFTER its publish date (oos_start_date) and store
    the result. Displaying that decayed-alpha number honestly beside the
    in-sample metrics is what stops the commons from becoming a lottery-ticket
    gallery. Runs daily; each listing is refreshed at most once every ~24h.
    """
    asyncio.run(_recompute_commons_oos_async())


async def _recompute_commons_oos_async() -> None:
    import json

    from app.services.backtest import run_backtest
    from app.services.market_data import get_bars

    pool = await _get_pool()
    try:
        rows = await pool.fetch(
            """
            SELECT ps.id, ps.strategy_id, ps.oos_start_date,
                   s.symbols, s.exchange, s.timeframe, s.risk_config,
                   sv.generated_logic
            FROM public_strategies ps
            JOIN strategies s ON s.id = ps.strategy_id
            JOIN strategy_versions sv ON sv.id = ps.published_version_id
            WHERE ps.is_listed
              AND ps.published_version_id IS NOT NULL
              AND ps.oos_start_date < now() - INTERVAL '1 day'
              AND (ps.oos_computed_at IS NULL OR ps.oos_computed_at < now() - INTERVAL '1 day')
            ORDER BY ps.oos_computed_at ASC NULLS FIRST
            LIMIT 50
            """
        )
        if not rows:
            logger.info("recompute_commons_oos: nothing due")
            return

        for row in rows:
            symbols = list(row["symbols"]) or []
            logic = row["generated_logic"] or ""
            if not symbols or len(logic.strip()) < 30:
                continue
            try:
                bars = await get_bars(
                    symbol=symbols[0].upper(),
                    exchange=(row["exchange"] or "NASDAQ").upper(),
                    timeframe=row["timeframe"],
                    limit=5_000,
                    pool=pool,
                    start=row["oos_start_date"],
                    end=None,
                )
                if not bars or len(bars) < 20:
                    logger.info(
                        "recompute_commons_oos: %s has too little OOS data (%d bars)",
                        row["id"],
                        len(bars) if bars else 0,
                    )
                    continue

                rc = row["risk_config"]
                if isinstance(rc, str):
                    try:
                        rc = json.loads(rc)
                    except Exception:
                        rc = {}
                risk_config = rc if isinstance(rc, dict) else {}

                result = await asyncio.to_thread(
                    run_backtest,
                    str(row["strategy_id"]),
                    logic,
                    bars,
                    row["timeframe"],
                    risk_config,
                    100_000.0,
                )
                m = result.metrics
                await pool.execute(
                    """
                    UPDATE public_strategies
                    SET oos_total_return_pct      = $1,
                        oos_annualized_return_pct = $2,
                        oos_sharpe_ratio          = $3,
                        oos_max_drawdown_pct      = $4,
                        oos_total_trades          = $5,
                        oos_computed_at           = now(),
                        updated_at                = now()
                    WHERE id = $6
                    """,
                    float(m.total_return_pct),
                    float(m.cagr_pct),
                    float(m.sharpe_ratio),
                    float(m.max_drawdown_pct),
                    int(m.total_trades),
                    row["id"],
                )
                logger.info(
                    "recompute_commons_oos: %s OOS return=%.2f%% sharpe=%.2f",
                    row["id"],
                    float(m.total_return_pct),
                    float(m.sharpe_ratio),
                )
            except Exception as exc:
                logger.warning("recompute_commons_oos: listing %s failed: %s", row["id"], exc)
    finally:
        await pool.close()


def _should_run_for_timeframe(
    timeframe: str,
    now_utc,
    last_run_at=None,
    exchange: str = "NASDAQ",
) -> bool:
    """
    Determine whether an active strategy should execute on this 1-minute Beat tick
    based on its timeframe and its most recent run timestamp.
    """
    from datetime import timezone

    import pytz

    from app.domain.market_hours import exchange_timezone

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    if last_run_at is not None and last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)

    tf = (timeframe or "1d").strip().lower()
    minute = now_utc.minute

    if tf in ("1m", "1min"):
        return True
    if tf in ("5m", "5min"):
        return minute % 5 == 0
    if tf in ("15m", "15min"):
        return minute % 15 == 0
    if tf in ("30m", "30min"):
        return minute % 30 == 0
    if tf in ("1h", "1hour", "60m", "60min"):
        return minute == 0
    if tf in ("4h", "4hour"):
        return minute == 0 and now_utc.hour % 4 == 0
    if tf in ("1w", "1week", "w", "weekly"):
        if last_run_at is None:
            return True
        tz = pytz.timezone(exchange_timezone(exchange))
        now_local = now_utc.astimezone(tz)
        last_local = last_run_at.astimezone(tz)
        return now_local.isocalendar()[:2] != last_local.isocalendar()[:2]
    # Default: daily ('1d', '1day', 'd', 'daily') — run once per local trading day
    if last_run_at is None:
        return True
    tz = pytz.timezone(exchange_timezone(exchange))
    return now_utc.astimezone(tz).date() != last_run_at.astimezone(tz).date()


@celery_app.task(name="app.worker.beat_tasks.poll_and_execute_active_strategies")
def poll_and_execute_active_strategies():
    """Poll and execute all active strategies on their timeframe cadence during open market sessions."""
    asyncio.run(_poll_and_execute_active_strategies_async())


async def _poll_and_execute_active_strategies_async() -> None:
    import json as _json
    from datetime import datetime, timezone

    from app.db.repositories.runs import RunRepo
    from app.domain.market_hours import get_session_status
    from app.worker.tasks import execute_trading_strategy

    now = datetime.now(timezone.utc)
    pool = await _get_pool()
    try:
        active_strats = await pool.fetch(
            """
            SELECT s.*, t.subscription_status,
                   (
                       SELECT MAX(sr.created_at)
                       FROM strategy_runs sr
                       WHERE sr.strategy_id = s.id
                   ) AS last_run_at
            FROM strategies s
            JOIN tenants t ON s.tenant_id = t.id
            WHERE s.status = 'active'
            """
        )
        if not active_strats:
            return

        for strat in active_strats:
            strategy_id = strat["id"]
            tenant_id = strat["tenant_id"]
            user_id = strat["owner_user_id"]
            exchange = strat["exchange"] or "NASDAQ"
            timeframe = (strat["timeframe"] or "1d").lower()
            risk_raw = strat["risk_config"]
            if isinstance(risk_raw, str):
                try:
                    risk_raw = _json.loads(risk_raw)
                except Exception:
                    risk_raw = {}
            risk_cfg = risk_raw if isinstance(risk_raw, dict) else {}

            # Market session check
            session = get_session_status(exchange, now)
            allowed_session = risk_cfg.get("trade_session", "regular")
            if session == "closed":
                continue
            if allowed_session in ("regular", "regular_only") and session != "open":
                continue

            # Respect SIP pause flag when strategy has a configured SIP schedule
            if strat.get("sip_monthly_amount") is not None and bool(strat.get("sip_paused", False)):
                continue

            # Timeframe cadence check (1m/5m/15m/30m/1h/4h/1d/1w)
            if not _should_run_for_timeframe(
                timeframe,
                now,
                last_run_at=strat.get("last_run_at"),
                exchange=exchange,
            ):
                continue

            # Determine dry_run: if paper_trading_only or subscription not active -> dry_run = True
            from app.services.billing import is_active_status

            paper_only = risk_cfg.get("paper_trading_only", True)
            is_sub_active = is_active_status(strat.get("subscription_status"))
            dry_run = paper_only or not is_sub_active

            # Prevent duplicate in-flight run
            in_flight = await pool.fetchval(
                """
                SELECT id FROM strategy_runs
                WHERE strategy_id = $1 AND status IN ('queued', 'running')
                LIMIT 1
                """,
                strategy_id,
            )
            if in_flight:
                continue

            # Create run record
            run_repo = RunRepo(pool, tenant_id)
            run = await run_repo.create(
                strategy_id=strategy_id,
                version_id=strat["current_version_id"],
                dry_run=dry_run,
            )

            try:
                task = execute_trading_strategy.apply_async(
                    args=[
                        str(strategy_id),
                        str(tenant_id),
                        str(user_id),
                        str(run["id"]),
                        dry_run,
                        list(strat["symbols"]),
                        str(strat.get("timeframe") or "1d"),
                        risk_cfg,
                    ],
                    queue="trading_tasks",
                )
                await run_repo.mark_dispatched(run["id"], task.id)
                logger.info(
                    "poll_and_execute_active_strategies: dispatched run %s (dry_run=%s) for strategy %s",
                    run["id"],
                    dry_run,
                    strat["name"],
                )
            except Exception as exc:
                logger.warning(
                    "poll_and_execute_active_strategies: dispatch failed for strategy %s: %s",
                    strategy_id,
                    exc,
                )
                try:
                    await run_repo.mark_failed(run["id"], str(exc))
                except Exception:
                    pass
    finally:
        await pool.close()

