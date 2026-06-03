"""
RunLogger — synchronous Redis publisher for use inside Celery tasks.

Celery workers are synchronous, so we use redis-py (sync client) to publish
log events to the run:{run_id} pub/sub channel. The async ws_manager
redis_listener picks these up and forwards them to connected WebSocket clients.

Message format (run_log):
  {"type": "run_log", "run_id": ..., "ts": ..., "level": ..., "msg": ..., "data": {...}}

Message format (run_status):
  {"type": "run_status", "run_id": ..., "ts": ..., "status": ..., "msg": ...}
"""
import json
import logging
from datetime import datetime, timezone
from typing import Literal

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

LogLevel = Literal["INFO", "WARN", "ERROR", "SIGNAL", "RISK", "ORDER", "STATUS"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLogger:
    """
    Drop-in logger for strategy execution workers.
    All messages are published to Redis and forwarded to the browser in real time.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.channel = f"run:{run_id}"
        settings = get_settings()
        self._r = redis.from_url(settings.redis_url, decode_responses=True)

    def _emit(self, level: LogLevel, msg: str, data: dict | None = None) -> None:
        payload: dict = {
            "type": "run_log",
            "run_id": self.run_id,
            "ts": _now(),
            "level": level,
            "msg": msg,
        }
        if data:
            payload["data"] = data
        try:
            self._r.publish(self.channel, json.dumps(payload))
        except Exception as exc:
            logger.warning("RunLogger publish failed: %s", exc)

    # ── Log level helpers ─────────────────────────────────────────────────────

    def info(self, msg: str, **data: object) -> None:
        self._emit("INFO", msg, dict(data) or None)

    def warn(self, msg: str, **data: object) -> None:
        self._emit("WARN", msg, dict(data) or None)

    def error(self, msg: str, **data: object) -> None:
        self._emit("ERROR", msg, dict(data) or None)

    def signal(self, msg: str, **data: object) -> None:
        """Emit a trading signal decision (BUY / SELL / HOLD)."""
        self._emit("SIGNAL", msg, dict(data) or None)

    def risk(self, msg: str, **data: object) -> None:
        """Emit a risk check result."""
        self._emit("RISK", msg, dict(data) or None)

    def order(self, msg: str, **data: object) -> None:
        """Emit an order placement event."""
        self._emit("ORDER", msg, dict(data) or None)

    # ── Status updates ────────────────────────────────────────────────────────

    def status(
        self,
        status: Literal["queued", "running", "completed", "failed", "rejected"],
        msg: str = "",
    ) -> None:
        """Publish a run_status event (updates the status badge in the UI)."""
        payload = {
            "type": "run_status",
            "run_id": self.run_id,
            "ts": _now(),
            "status": status,
            "msg": msg,
        }
        try:
            self._r.publish(self.channel, json.dumps(payload))
        except Exception as exc:
            logger.warning("RunLogger status publish failed: %s", exc)

    def close(self) -> None:
        try:
            self._r.close()
        except Exception:
            pass
