"""
Social copy-trading API — the public "Swarm" leaderboard + publish/subscribe.

The leaderboard is a cross-tenant marketplace view (every tenant's published
strategies); publish/subscribe writes are scoped to the caller's tenant via
SocialRepo. The platform never holds funds — a subscription dedicates the
subscriber's OWN buying power, and copied trades fan out into their own broker
account at signal time (see app/services/execution.fan_out_to_subscribers).
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.social import SocialRepo

router = APIRouter(prefix="/v1/social", tags=["social"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class LeaderboardEntry(BaseModel):
    public_strategy_id: str
    strategy_id: str
    title: str
    description: str
    creator_name: str
    symbols: list[str]
    exchange: str
    management_fee_bps: int
    subscriber_count: int
    fork_count: int
    forked_from_public_strategy_id: str | None
    is_verified: bool
    # Latest-backtest metrics — null when the strategy has never been backtested.
    cagr_pct: float | None
    total_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    win_rate_pct: float | None
    total_trades: int | None


class PublishRequest(BaseModel):
    strategy_id: str
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=2_000)
    # Capped at 20% (2000 bps). A 100% fee listing is either a typo or predatory;
    # no legitimate strategy charges more than hedge-fund territory.
    management_fee_bps: int = Field(default=0, ge=0, le=2_000)


class PublishResponse(BaseModel):
    public_strategy_id: str
    strategy_id: str
    title: str
    management_fee_bps: int
    subscriber_count: int
    is_verified: bool


class SubscribeRequest(BaseModel):
    allocated_capital: float = Field(
        gt=0, description="Buying power to dedicate to this copied strategy"
    )


class SubscribeResponse(BaseModel):
    subscription_id: str
    public_strategy_id: str
    allocated_capital: float
    is_active: bool


class SubscriptionEntry(BaseModel):
    subscription_id: str
    public_strategy_id: str
    strategy_id: str
    title: str
    allocated_capital: float
    management_fee_bps: int
    subscriber_count: int


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[LeaderboardEntry]:
    """Ranked public strategies, sorted by Sharpe then CAGR (risk-adjusted return)."""
    repo = SocialRepo(pool, current_user.tenant_id)
    rows = await repo.leaderboard(limit=limit)
    return [
        LeaderboardEntry(
            public_strategy_id=str(r["id"]),
            strategy_id=str(r["strategy_id"]),
            title=r["title"],
            description=r["description"],
            creator_name=r["creator_name"],
            symbols=list(r["symbols"]),
            exchange=r["exchange"],
            management_fee_bps=int(r["management_fee_bps"]),
            subscriber_count=int(r["subscriber_count"]),
            fork_count=int(r["fork_count"]),
            forked_from_public_strategy_id=(
                str(r["forked_from_public_strategy_id"])
                if r["forked_from_public_strategy_id"]
                else None
            ),
            is_verified=bool(r["is_verified"]),
            cagr_pct=_f(r["cagr_pct"]),
            total_return_pct=_f(r["total_return_pct"]),
            sharpe_ratio=_f(r["sharpe_ratio"]),
            max_drawdown_pct=_f(r["max_drawdown_pct"]),
            win_rate_pct=_f(r["win_rate_pct"]),
            total_trades=int(r["total_trades"]) if r["total_trades"] is not None else None,
        )
        for r in rows
    ]


@router.post("/publish", response_model=PublishResponse, status_code=status.HTTP_201_CREATED)
async def publish_strategy(
    request: PublishRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> PublishResponse:
    """Publish one of the caller's private strategies to the public leaderboard."""
    try:
        strategy_uuid = UUID(request.strategy_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid strategy_id"
        ) from exc

    repo = SocialRepo(pool, current_user.tenant_id)
    row = await repo.publish(
        strategy_id=strategy_uuid,
        creator_user_id=current_user.user_id,
        title=request.title,
        description=request.description,
        management_fee_bps=request.management_fee_bps,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or not owned by your account.",
        )
    return PublishResponse(
        public_strategy_id=str(row["id"]),
        strategy_id=str(row["strategy_id"]),
        title=row["title"],
        management_fee_bps=int(row["management_fee_bps"]),
        subscriber_count=int(row["subscriber_count"]),
        is_verified=bool(row["is_verified"]),
    )


class ForkResponse(BaseModel):
    strategy_id: str
    name: str
    forked_from_public_strategy_id: str


class LineageNode(BaseModel):
    public_strategy_id: str
    title: str


class LineageChild(BaseModel):
    public_strategy_id: str
    title: str
    creator_name: str
    subscriber_count: int
    fork_count: int
    sharpe_ratio: float | None
    cagr_pct: float | None


class LineageResponse(BaseModel):
    # Ancestors ordered nearest-parent first; children ranked by Sharpe.
    ancestors: list[LineageNode]
    children: list[LineageChild]


@router.post("/fork/{public_strategy_id}", response_model=ForkResponse, status_code=status.HTTP_201_CREATED)
async def fork_strategy(
    public_strategy_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> ForkResponse:
    """
    Fork a published strategy into a new private strategy you own — the copied
    code is the listing's pinned immutable version. Editing your fork and
    re-publishing it grows the lineage graph.
    """
    repo = SocialRepo(pool, current_user.tenant_id)
    try:
        row = await repo.fork(public_strategy_id, current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public strategy not found.")
    return ForkResponse(
        strategy_id=str(row["id"]),
        name=row["name"],
        forked_from_public_strategy_id=str(public_strategy_id),
    )


@router.get("/lineage/{public_strategy_id}", response_model=LineageResponse)
async def get_lineage(
    public_strategy_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> LineageResponse:
    """The fork graph around a listing: ancestor chain + direct descendants."""
    repo = SocialRepo(pool, current_user.tenant_id)
    graph = await repo.lineage(public_strategy_id)
    return LineageResponse(
        ancestors=[
            LineageNode(public_strategy_id=str(a["id"]), title=a["title"])
            for a in graph["ancestors"]
        ],
        children=[
            LineageChild(
                public_strategy_id=str(c["id"]),
                title=c["title"],
                creator_name=c["creator_name"],
                subscriber_count=int(c["subscriber_count"]),
                fork_count=int(c["fork_count"]),
                sharpe_ratio=_f(c["sharpe_ratio"]),
                cagr_pct=_f(c["cagr_pct"]),
            )
            for c in graph["children"]
        ],
    )


@router.post("/subscribe/{public_strategy_id}", response_model=SubscribeResponse)
async def subscribe_strategy(
    public_strategy_id: UUID,
    request: SubscribeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> SubscribeResponse:
    """Copy a published strategy, dedicating buying power to it."""
    repo = SocialRepo(pool, current_user.tenant_id)
    try:
        row = await repo.subscribe(
            public_strategy_id=public_strategy_id,
            subscriber_user_id=current_user.user_id,
            allocated_capital=request.allocated_capital,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SubscribeResponse(
        subscription_id=str(row["id"]),
        public_strategy_id=str(row["public_strategy_id"]),
        allocated_capital=float(row["allocated_capital"]),
        is_active=bool(row["is_active"]),
    )


@router.delete("/subscribe/{public_strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_strategy(
    public_strategy_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    repo = SocialRepo(pool, current_user.tenant_id)
    removed = await repo.unsubscribe(public_strategy_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found."
        )


@router.get("/subscriptions", response_model=list[SubscriptionEntry])
async def list_subscriptions(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[SubscriptionEntry]:
    repo = SocialRepo(pool, current_user.tenant_id)
    rows = await repo.list_subscriptions()
    return [
        SubscriptionEntry(
            subscription_id=str(r["id"]),
            public_strategy_id=str(r["public_strategy_id"]),
            strategy_id=str(r["strategy_id"]),
            title=r["title"],
            allocated_capital=float(r["allocated_capital"]),
            management_fee_bps=int(r["management_fee_bps"]),
            subscriber_count=int(r["subscriber_count"]),
        )
        for r in rows
    ]


def _f(v) -> float | None:
    return float(v) if v is not None else None
