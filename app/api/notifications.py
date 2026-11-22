"""
Notifications API — GET list / unread-count, POST mark-read / read-all.

Real-time delivery is over /v1/ws/portfolio (see app/services/notifications.py);
this router serves history and read-state for the notification panel.
"""

import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.notifications import NotificationRepo
from app.services.notifications import notification_to_dict

logger = logging.getLogger(__name__)

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


@router.post("/{notif_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_notification(
    notif_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    """
    Approve a rebalance_approval notification.
    Marks it as read + sets approved_at timestamp, and dispatches the
    approved strategy rebalance run to Celery immediately.
    """
    from app.db.repositories.runs import RunRepo
    from app.db.repositories.strategies import StrategyRepo
    from app.db.repositories.users import TenantRepo
    from app.services.billing import is_active_status
    from app.worker.tasks import execute_trading_strategy

    repo = NotificationRepo(pool, current_user.tenant_id)
    notif = await repo.get_by_id(notif_id)
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if notif["type"] != "rebalance_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only rebalance_approval notifications can be approved",
        )
    if notif.get("approved_at") is not None:
        return  # already approved — idempotent

    await repo.approve(notif_id, current_user.user_id)

    if notif.get("entity_type") == "strategy" and notif.get("entity_id"):
        strat_repo = StrategyRepo(pool, current_user.tenant_id)
        record = await strat_repo.get_by_id(notif["entity_id"])
        if not record:
            return

        risk_raw = record["risk_config"]
        if isinstance(risk_raw, str):
            try:
                risk_raw = json.loads(risk_raw)
            except Exception:
                risk_raw = {}
        risk_cfg = risk_raw if isinstance(risk_raw, dict) else {}

        paper_only = bool(risk_cfg.get("paper_trading_only", True))
        tenant = await TenantRepo(pool).get_by_id(current_user.tenant_id)
        is_sub_active = bool(tenant and is_active_status(tenant.get("subscription_status")))
        dry_run = paper_only or not is_sub_active

        run_repo = RunRepo(pool, current_user.tenant_id)
        run = await run_repo.create(
            strategy_id=record["id"],
            version_id=record["current_version_id"],
            dry_run=dry_run,
        )
        try:
            task = execute_trading_strategy.apply_async(
                args=[
                    str(record["id"]),
                    str(current_user.tenant_id),
                    str(current_user.user_id),
                    str(run["id"]),
                    dry_run,
                    list(record["symbols"]),
                    str(record.get("timeframe") or "1d"),
                    risk_cfg,
                ],
                queue="trading_tasks",
            )
            await run_repo.mark_dispatched(run["id"], task.id)
        except Exception as exc:
            logger.warning("Approved rebalance dispatch failed for strategy %s: %s", record["id"], exc)
            try:
                await run_repo.mark_failed(run["id"], str(exc))
            except Exception:
                pass
