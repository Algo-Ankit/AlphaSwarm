"""
Notifications API — GET list / unread-count, POST mark-read / read-all.

Real-time delivery is over /v1/ws/portfolio (see app/services/notifications.py);
this router serves history and read-state for the notification panel.
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.notifications import NotificationRepo
from app.services.notifications import notification_to_dict

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    entity_type: str | None
    entity_id: str | None
    is_read: bool
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[NotificationResponse]:
    repo = NotificationRepo(pool, current_user.tenant_id)
    rows = await repo.list(current_user.user_id, unread_only=unread_only, limit=limit)
    return [NotificationResponse(**notification_to_dict(r)) for r in rows]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> UnreadCountResponse:
    repo = NotificationRepo(pool, current_user.tenant_id)
    return UnreadCountResponse(count=await repo.unread_count(current_user.user_id))


@router.post("/{notif_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notif_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    repo = NotificationRepo(pool, current_user.tenant_id)
    result = await repo.mark_read(notif_id, current_user.user_id)
    if result.endswith("0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    repo = NotificationRepo(pool, current_user.tenant_id)
    await repo.mark_all_read(current_user.user_id)
