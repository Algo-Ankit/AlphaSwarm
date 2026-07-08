"""Repository for the Swarm Creator Social Feed."""

from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class FeedRepo(BaseRepo):
    """Tenant-scoped writes; timeline is a cross-tenant read prioritising subscriptions."""

    async def create_post(
        self,
        content_markdown: str,
        public_strategy_id: UUID | None,
    ) -> asyncpg.Record:
        return await self.fetchrow(
            """
            INSERT INTO social_posts (tenant_id, public_strategy_id, content_markdown)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            self.tenant_id,
            public_strategy_id,
            content_markdown,
        )

    async def timeline(self, limit: int = 50, offset: int = 0) -> list[asyncpg.Record]:
        """
        Cross-tenant reverse-chronological feed.
        Posts from strategies the caller subscribes to are surfaced first.
        """
        return await self.fetch(
            """
            SELECT
                sp.id,
                sp.tenant_id            AS author_tenant_id,
                sp.public_strategy_id,
                sp.content_markdown,
                sp.likes_count,
                sp.created_at,
                t.name                  AS author_name,
                ps.title                AS strategy_title,
                ps.creator_tenant_id,
                bt.annualized_return_pct AS cagr_pct,
                bt.sharpe_ratio,
                CASE WHEN sub.id IS NOT NULL THEN 1 ELSE 0 END AS subscribed_boost,
                (pl.post_id IS NOT NULL) AS liked_by_me
            FROM social_posts sp
            JOIN tenants t ON t.id = sp.tenant_id
            LEFT JOIN public_strategies ps ON ps.id = sp.public_strategy_id
            LEFT JOIN strategy_subscriptions sub
                ON  sub.public_strategy_id = sp.public_strategy_id
                AND sub.subscriber_tenant_id = $1
                AND sub.is_active
            LEFT JOIN social_post_likes pl
                ON  pl.post_id = sp.id
                AND pl.tenant_id = $1
            LEFT JOIN LATERAL (
                SELECT b.annualized_return_pct, b.sharpe_ratio
                FROM backtest_results b
                WHERE b.strategy_id = ps.strategy_id
                ORDER BY b.created_at DESC
                LIMIT 1
            ) bt ON TRUE
            ORDER BY subscribed_boost DESC, sp.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            self.tenant_id,
            limit,
            offset,
        )

    async def toggle_like(self, post_id: UUID) -> asyncpg.Record | None:
        """
        Idempotent like toggle for the calling tenant. Atomic: the likes_count
        denormalization moves in lockstep with the social_post_likes row inside
        one transaction. Returns (liked, likes_count), or None if the post
        doesn't exist.
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval(
                    "SELECT 1 FROM social_posts WHERE id = $1", post_id
                )
                if not exists:
                    return None

                removed = await conn.fetchrow(
                    "DELETE FROM social_post_likes WHERE post_id = $1 AND tenant_id = $2 RETURNING post_id",
                    post_id,
                    self.tenant_id,
                )
                if removed is not None:
                    return await conn.fetchrow(
                        """
                        UPDATE social_posts
                        SET likes_count = GREATEST(likes_count - 1, 0)
                        WHERE id = $1
                        RETURNING FALSE AS liked, likes_count
                        """,
                        post_id,
                    )

                await conn.execute(
                    "INSERT INTO social_post_likes (post_id, tenant_id) VALUES ($1, $2)",
                    post_id,
                    self.tenant_id,
                )
                return await conn.fetchrow(
                    """
                    UPDATE social_posts
                    SET likes_count = likes_count + 1
                    WHERE id = $1
                    RETURNING TRUE AS liked, likes_count
                    """,
                    post_id,
                )
