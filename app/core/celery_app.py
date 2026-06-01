from celery import Celery
import os

# Use Redis as the message broker and result backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "alphaswarm_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Route all trading tasks to a dedicated queue
celery_app.conf.task_routes = {
    "app.worker.tasks.*": {"queue": "trading_tasks"}
}
celery_app.conf.update(task_track_started=True)
