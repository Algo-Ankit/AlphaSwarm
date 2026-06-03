"""
Celery Beat periodic tasks.
These are stubs — real implementations added in Phase 3 and Phase 4
once the DB layer and intelligence services are in place.
"""
from app.core.celery_app import celery_app


@celery_app.task(name="app.worker.beat_tasks.snapshot_portfolio")
def snapshot_portfolio():
    """
    Write a portfolio_snapshots row for every active tenant.
    Runs every 5 minutes. Powers the equity curve on the dashboard.
    Implemented in Phase 4 (requires DB + positions table).
    """


@celery_app.task(name="app.worker.beat_tasks.refresh_active_symbols_news")
def refresh_active_symbols_news():
    """
    Fetch latest news for all symbols with active running strategies.
    Runs every hour. Implemented in Phase 3 (requires news_intel service).
    """


@celery_app.task(name="app.worker.beat_tasks.refresh_stale_forecasts")
def refresh_stale_forecasts():
    """
    Regenerate forecasts older than 1 hour for actively watched symbols.
    Runs every hour at :30. Implemented in Phase 3 (requires forecaster service).
    """


@celery_app.task(name="app.worker.beat_tasks.check_worker_heartbeats")
def check_worker_heartbeats():
    """
    Check Redis for strategy worker heartbeat keys.
    If any run_id key is stale (> 30s), mark that run as ERROR
    and trigger a notification. Implemented in Phase 4.
    """


@celery_app.task(name="app.worker.beat_tasks.reconcile_positions")
def reconcile_positions():
    """
    End-of-day: compare positions table against actual broker positions.
    Flag any discrepancy in audit_events. Implemented in Phase 4.
    """
