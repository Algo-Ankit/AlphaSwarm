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
                # Today's realized P&L
                realized_row = await pool.fetchrow(
                    """
                    SELECT COALESCE(SUM(realized_pnl), 0) AS realized
                    FROM positions
                    WHERE tenant_id = $1
                    """,
                    tenant_id,
                )
                # Use broker account equity if available; fall back to 0
                open_pnl = Decimal(str(pnl_row["open_pnl"] or 0))
                realized_today = Decimal(str(realized_row["realized"] or 0))
                active = int(pnl_row["active_strategies"] or 0)

                await pool.execute(
                    """
                    INSERT INTO portfolio_snapshots
                        (tenant_id, total_equity, cash_balance, open_pnl, realized_pnl_today, active_strategies)
                    VALUES ($1, $2, NULL, $3, $4, $5)
                    """,
                    tenant_id,
                    float(open_pnl + realized_today),
                    float(open_pnl),
                    float(realized_today),
                    active,
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
                logger.info(
                    "  %s (%s): %d news items cached", symbol, exchange, len(items)
                )
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

        logger.info(
            "refresh_stale_forecasts: checking %d symbols", len(active)
        )
        now = datetime.now(timezone.utc)

        for symbol, exchange in active:
            try:
                cached = await fc_repo.get_latest(symbol, exchange, horizon_days=5)
                if cached:
                    gen_at = cached["generated_at"]
                    if gen_at.tzinfo is None:
                        gen_at = gen_at.replace(tzinfo=timezone.utc)
                    if (now - gen_at) < _STALE_THRESHOLD:
                        logger.info(
                            "  %s (%s): forecast fresh, skipping", symbol, exchange
                        )
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
                logger.warning(
                    "  %s (%s): forecast refresh failed: %s", symbol, exchange, exc
                )
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.check_worker_heartbeats")
def check_worker_heartbeats():
    """Mark runs stuck in 'running' > 90s with no DB update as failed."""
    asyncio.run(_check_heartbeats_async())


async def _check_heartbeats_async() -> None:
    from uuid import UUID

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
                run_id, tenant_id,
            )
            logger.warning("  marked run %s as failed (heartbeat timeout)", run_id)
    finally:
        await pool.close()


@celery_app.task(name="app.worker.beat_tasks.reconcile_positions")
def reconcile_positions():
    """End-of-day: compare DB positions against actual broker positions."""
    asyncio.run(_reconcile_positions_async())


async def _reconcile_positions_async() -> None:
    from decimal import Decimal
    from uuid import UUID

    pool = await _get_pool()
    try:
        brokers = await pool.fetch(
            "SELECT * FROM broker_connections WHERE is_active = true AND broker = 'alpaca'"
        )
        if not brokers:
            logger.info("reconcile_positions: no active Alpaca connections")
            return

        from app.services.broker_crypto import decrypt_key
        from app.services.execution import AlpacaExecutor

        for row in brokers:
            tenant_id = row["tenant_id"]
            try:
                executor = AlpacaExecutor(
                    api_key=decrypt_key(row["key_encrypted"]),
                    secret_key=decrypt_key(row["secret_encrypted"]),
                    paper=bool(row["is_paper"]),
                )
                broker_positions = executor.get_positions()

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
                            tenant_id, symbol, db_qty, broker_qty, diff,
                        )

                logger.info(
                    "reconcile_positions: tenant=%s  broker_positions=%d  db_positions=%d",
                    tenant_id, len(broker_positions), len(db_positions),
                )
            except Exception as exc:
                logger.warning("reconcile_positions: tenant %s failed: %s", tenant_id, exc)
    finally:
        await pool.close()
