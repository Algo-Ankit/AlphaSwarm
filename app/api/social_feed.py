"""
Creator Social Feed — publish updates and consume a prioritised timeline.

POST /v1/feed/post      → creator publishes a markdown update, optionally linked to a public strategy
GET  /v1/feed/timeline  → cross-tenant chronological feed; subscribed-strategy posts are boosted
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.rate_limit import limiter
from app.db.repositories.social_feed import FeedRepo

router = APIRouter(prefix="/v1/feed", tags=["feed"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class PostRequest(BaseModel):
    content_markdown: str = Field(min_length=1, max_length=5_000)
    public_strategy_id: str | None = Field(default=None)


class PostResponse(BaseModel):
    id: str
    author_tenant_id: str
    author_name: str
    public_strategy_id: str | None
    content_markdown: str
    likes_count: int
    created_at: str


class TimelinePost(BaseModel):
    id: str
    author_tenant_id: str
    author_name: str
    public_strategy_id: str | None
    strategy_title: str | None
    cagr_pct: float | None
    sharpe_ratio: float | None
    content_markdown: str
    likes_count: int
    created_at: str
    is_subscribed: bool
    liked_by_me: bool


class LikeResponse(BaseModel):
    post_id: str
    liked: bool
    likes_count: int


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/post", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # anti-spam: the feed is cross-tenant and public
async def create_post(
    request: Request,
    body: PostRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> PostResponse:
    """Publish a feed update. Optionally link it to one of your public strategies."""
    pub_id: UUID | None = None
    if body.public_strategy_id:
        try:
            pub_id = UUID(body.public_strategy_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid public_strategy_id",
            ) from exc
        owned = await pool.fetchrow(
            "SELECT id FROM public_strategies WHERE id = $1 AND creator_tenant_id = $2",
            pub_id,
            current_user.tenant_id,
        )
        if owned is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only link posts to your own published strategies.",
            )

    repo = FeedRepo(pool, current_user.tenant_id)
    row = await repo.create_post(body.content_markdown, pub_id)
    tenant = await pool.fetchrow("SELECT name FROM tenants WHERE id = $1", current_user.tenant_id)
    return PostResponse(
        id=str(row["id"]),
        author_tenant_id=str(row["tenant_id"]),
        author_name=tenant["name"] if tenant else "Unknown",
        public_strategy_id=str(row["public_strategy_id"]) if row["public_strategy_id"] else None,
        content_markdown=row["content_markdown"],
        likes_count=int(row["likes_count"]),
        created_at=row["created_at"].isoformat(),
    )


@router.get("/timeline", response_model=list[TimelinePost])
async def get_timeline(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[TimelinePost]:
    """
    Cross-tenant feed, newest-first.
    Posts from strategies the caller subscribes to appear before the rest.
    """
    repo = FeedRepo(pool, current_user.tenant_id)
    rows = await repo.timeline(limit=limit, offset=offset)
    return [
        TimelinePost(
            id=str(r["id"]),
            author_tenant_id=str(r["author_tenant_id"]),
            author_name=r["author_name"],
            public_strategy_id=str(r["public_strategy_id"]) if r["public_strategy_id"] else None,
            strategy_title=r["strategy_title"],
            cagr_pct=float(r["cagr_pct"]) if r["cagr_pct"] is not None else None,
            sharpe_ratio=float(r["sharpe_ratio"]) if r["sharpe_ratio"] is not None else None,
            content_markdown=r["content_markdown"],
            likes_count=int(r["likes_count"]),
            created_at=r["created_at"].isoformat(),
            is_subscribed=bool(r["subscribed_boost"]),
            liked_by_me=bool(r["liked_by_me"]),
        )
        for r in rows
    ]


@router.post("/{post_id}/like", response_model=LikeResponse)
async def toggle_like(
    post_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> LikeResponse:
    """Toggle the caller's like on a post (one like per tenant, idempotent)."""
    repo = FeedRepo(pool, current_user.tenant_id)
    row = await repo.toggle_like(post_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return LikeResponse(
        post_id=str(post_id),
        liked=bool(row["liked"]),
        likes_count=int(row["likes_count"]),
    )
