"""
Process-wide cached Redis clients.

`redis.from_url(...)` builds a brand-new client (and its own connection pool)
on every call. Code paths that did this per run/publish — RunLogger, the beat
publisher, the notification fan-out — churned through TCP sockets and could
exhaust the connection limit under load. These accessors hand back a single
client per process whose internal pool is reused across calls.

Two flavours:
  • get_sync_redis()  — redis-py sync client, for Celery workers (sync context).
  • get_async_redis() — redis.asyncio client, for FastAPI / async code.

Both are created lazily and cached. Do NOT .close() the returned client; it is
shared for the lifetime of the process.
"""
from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_sync_redis() -> redis.Redis:
    """Shared synchronous Redis client (decoded responses)."""
    return redis.from_url(get_settings().redis_url, decode_responses=True)


@lru_cache(maxsize=1)
def get_async_redis() -> aioredis.Redis:
    """Shared asyncio Redis client (decoded responses)."""
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)
