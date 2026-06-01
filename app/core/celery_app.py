from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "alphaswarm_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.task_routes = {
    "app.worker.tasks.*": {"queue": "trading_tasks"}
}
celery_app.conf.update(
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
