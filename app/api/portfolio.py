"""
Portfolio API — GET /summary (latest snapshot) + GET /snapshots (equity curve).

Snapshots are written every 5 min by app.worker.beat_tasks.snapshot_portfolio,
which also publishes a live update to /v1/ws/portfolio. The platform never holds
funds — total_equity/open_pnl are display aggregates derived from positions and
the user's own broker account; cash_balance is a nullable display snapshot.
"""
import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.portfolio import PortfolioRepo

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])


class PortfolioSummary(BaseModel):
    snapshot_time: str | None
    total_equity: float
    open_pnl: float
    realized_pnl_today: float
    active_strategies: int
    has_data: bool


class SnapshotPoint(BaseModel):
    snapshot_time: str
    total_equity: float
    open_pnl: float
    realized_pnl_today: float
    active_strategies: int


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> PortfolioSummary:
    repo = PortfolioRepo(pool, current_user.tenant_id)
    row = await repo.latest()
    if not row:
        return PortfolioSummary(
            snapshot_time=None, total_equity=0.0, open_pnl=0.0,
            realized_pnl_today=0.0, active_strategies=0, has_data=False,
        )
    return PortfolioSummary(
        snapshot_time=row["snapshot_time"].isoformat(),
        total_equity=float(row["total_equity"]),
        open_pnl=float(row["open_pnl"]),
        realized_pnl_today=float(row["realized_pnl_today"]),
        active_strategies=int(row["active_strategies"]),
        has_data=True,
    )


@router.get("/snapshots", response_model=list[SnapshotPoint])
async def get_snapshots(
    limit: int = Query(200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[SnapshotPoint]:
    repo = PortfolioRepo(pool, current_user.tenant_id)
    rows = await repo.history(limit=limit)
    return [
        SnapshotPoint(
            snapshot_time=r["snapshot_time"].isoformat(),
            total_equity=float(r["total_equity"]),
            open_pnl=float(r["open_pnl"]),
            realized_pnl_today=float(r["realized_pnl_today"]),
            active_strategies=int(r["active_strategies"]),
        )
        for r in rows
    ]
