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
    """
    Write a portfolio_snapshots row for every active tenant.
    Runs every 5 minutes. Powers the equity curve on the dashboard.
    Implemented in Phase 4 (requires positions table + execution engine).
    """


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
    """
    Check Redis for strategy worker heartbeat keys.
    If any run_id key is stale (> 30s), mark that run as ERROR.
    Implemented in Phase 4.
    """


@celery_app.task(name="app.worker.beat_tasks.reconcile_positions")
def reconcile_positions():
    """
    End-of-day: compare positions table against actual broker positions.
    Flag any discrepancy in audit_events. Implemented in Phase 4.
    """
