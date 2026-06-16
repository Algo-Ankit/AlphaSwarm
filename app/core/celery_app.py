from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

# ── Sentry (worker-side error + performance monitoring) ────────────────────────
# Initialised at module import so every Celery worker/beat process is covered.
# The CeleryIntegration captures unhandled task exceptions + soft/hard timeouts.
# No-op when SENTRY_DSN is unset.
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[CeleryIntegration()],
        send_default_pii=False,
    )

celery_app = Celery(
    "alphaswarm_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    # ── Serialization ────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Routing ──────────────────────────────────────────────
    task_routes={
        "app.worker.tasks.*":      {"queue": "trading_tasks"},
        "app.worker.beat_tasks.*": {"queue": "beat_tasks"},
    },
    task_default_queue="trading_tasks",
    # ── Reliability (critical for trading) ───────────────────
    task_acks_late=True,               # ack only after task completes, not on receipt
    task_reject_on_worker_lost=True,   # re-queue if worker process dies mid-task
    worker_prefetch_multiplier=1,      # one task at a time per worker process
                                       # (trading isolation — don't batch strategy tasks)
    # ── Worker lifecycle ─────────────────────────────────────
    worker_max_tasks_per_child=50,     # recycle worker process every 50 tasks (prevents leaks)
    worker_max_memory_per_child=400_000,  # kill worker if it exceeds 400MB RSS
    # ── Task timeouts ────────────────────────────────────────
    task_soft_time_limit=3_600,        # 1 hour soft limit — task gets SoftTimeLimitExceeded
    task_time_limit=3_660,             # 1 hour 1 min hard kill — SIGKILL
    # ── Results ──────────────────────────────────────────────
    result_expires=86_400,             # keep results in Redis for 24 hours
    task_track_started=True,
    # ── Dev mode ─────────────────────────────────────────────
    task_always_eager=settings.celery_task_always_eager,
    # ── Beat schedule (periodic tasks) ───────────────────────
    beat_schedule={
        # Portfolio snapshot every 5 minutes — powers the equity curve
        "portfolio-snapshot": {
            "task": "app.worker.beat_tasks.snapshot_portfolio",
            "schedule": crontab(minute="*/5"),
            "options": {"queue": "beat_tasks"},
        },
        # Refresh news for all active strategy symbols — every hour
        "refresh-news": {
            "task": "app.worker.beat_tasks.refresh_active_symbols_news",
            "schedule": crontab(minute=0),
            "options": {"queue": "beat_tasks"},
        },
        # Regenerate stale forecasts (> 1hr old) — every hour, offset 30 min
        "refresh-forecasts": {
            "task": "app.worker.beat_tasks.refresh_stale_forecasts",
            "schedule": crontab(minute=30),
            "options": {"queue": "beat_tasks"},
        },
        # Heartbeat monitor — checks if any strategy workers have gone silent
        "worker-heartbeat-check": {
            "task": "app.worker.beat_tasks.check_worker_heartbeats",
            "schedule": 30.0,  # every 30 seconds
            "options": {"queue": "beat_tasks"},
        },
        # End-of-day position reconciliation — 5:10 PM New York (after NYSE close)
        "reconcile-positions": {
            "task": "app.worker.beat_tasks.reconcile_positions",
            "schedule": crontab(hour=17, minute=10),
            "options": {"queue": "beat_tasks"},
        },
    },
)
