"""
Notification creation + real-time fan-out.

A notification is persisted to the `notifications` table AND published to the
tenant's portfolio Redis channel (`portfolio:{tenant_id}`), which the async
ws_manager bridge forwards to any connected `/v1/ws/portfolio` clients. This is
the single place trade/bot/system events become user-visible notifications.

create_notification is always awaited from an async context (FastAPI routes and
the asyncpg-based worker loop), so the Redis fan-out uses the shared asyncio
client — a blocking sync publish would stall the event loop. The DB insert is
async (asyncpg).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.redis_pool import get_async_redis

logger = logging.getLogger(__name__)

NotificationType = str  # trade_executed | bot_error | pnl_threshold | news | system


def _to_uuid(v: Any) -> UUID | None:
    if v is None or isinstance(v, UUID):
        return v
    return UUID(str(v))


def notification_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "entity_type": row["entity_type"],
        "entity_id": str(row["entity_id"]) if row["entity_id"] else None,
        "is_read": row["is_read"],
        "created_at": row["created_at"].isoformat(),
    }


async def _publish(channel: str, payload: dict) -> None:
    try:
        # Shared async client — non-blocking, never per-call created/closed.
        await get_async_redis().publish(channel, json.dumps(payload))
    except Exception as exc:  # pragma: no cover - best effort fan-out
        logger.warning("notification publish failed on %s: %s", channel, exc)


async def create_notification(
    conn: Any,
    *,
    tenant_id: Any,
    user_id: Any = None,
    type: NotificationType,
    title: str,
    body: str,
    entity_type: str | None = None,
    entity_id: Any = None,
) -> dict:
    """Persist a notification and fan it out over the portfolio WS channel.

    `conn` is an asyncpg connection/pool-acquired connection. `user_id` may be
    None for tenant-wide notifications (visible to all users in the tenant).
    """
    tid = _to_uuid(tenant_id)
    row = await conn.fetchrow(
        """
        INSERT INTO notifications
            (tenant_id, user_id, type, title, body, entity_type, entity_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        tid, _to_uuid(user_id), type, title, body, entity_type, _to_uuid(entity_id),
    )
    payload = {
        "type": "notification",
        "ts": datetime.now(timezone.utc).isoformat(),
        "notification": notification_to_dict(row),
    }
    await _publish(f"portfolio:{tid}", payload)
    return notification_to_dict(row)
