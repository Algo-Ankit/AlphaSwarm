"""
Social copy-trading repository.

Unlike most repos, the leaderboard is a CROSS-TENANT read: the public "Swarm"
leaderboard surfaces strategies published by every tenant, so those queries
intentionally do NOT filter on self.tenant_id. Writes remain tenant-scoped:
- publish() only lists a strategy the calling tenant owns,
- subscribe()/list_subscriptions() are keyed on the subscriber's tenant_id.
"""

from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class SocialRepo(BaseRepo):
    # ── Leaderboard (cross-tenant read) ────────────────────────────────────────
    async def leaderboard(self, limit: int = 50) -> list[asyncpg.Record]:
        """
        Ranked list of public strategies. Each row is enriched with the strategy's
        latest backtest metrics (CAGR / Sharpe / drawdown / win-rate) and ranked by
        risk-adjusted return: Sharpe first, then annualized return (CAGR).
        """
        return await self.fetch(
            """
            SELECT
                ps.id,
                ps.strategy_id,
                ps.creator_tenant_id,
                ps.title,
                ps.description,
                ps.management_fee_bps,
                ps.subscriber_count,
                ps.is_verified,
                ps.created_at,
                s.name      AS strategy_name,
                s.symbols   AS symbols,
                s.exchange  AS exchange,
                t.name      AS creator_name,
                bt.annualized_return_pct AS cagr_pct,
                bt.total_return_pct,
                bt.sharpe_ratio,
                bt.max_drawdown_pct,
                bt.win_rate_pct,
                bt.total_trades
            FROM public_strategies ps
            JOIN strategies s ON s.id = ps.strategy_id
            JOIN tenants   t ON t.id = ps.creator_tenant_id
            LEFT JOIN LATERAL (
                SELECT b.annualized_return_pct, b.total_return_pct, b.sharpe_ratio,
                       b.max_drawdown_pct, b.win_rate_pct, b.total_trades
                FROM backtest_results b
                WHERE b.strategy_id = ps.strategy_id
                ORDER BY b.created_at DESC
                LIMIT 1
            ) bt ON TRUE
            WHERE ps.is_listed
            ORDER BY COALESCE(bt.sharpe_ratio, 0) DESC,
                     COALESCE(bt.annualized_return_pct, 0) DESC,
                     ps.subscriber_count DESC
            LIMIT $1
            """,
            limit,
        )

    async def get_public(self, public_strategy_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT * FROM public_strategies WHERE id = $1 AND is_listed",
            public_strategy_id,
        )

    # ── Publish (tenant-scoped write) ──────────────────────────────────────────
    async def publish(
        self,
        strategy_id: UUID,
        creator_user_id: UUID,
        title: str,
        description: str,
        management_fee_bps: int,
    ) -> asyncpg.Record | None:
        """
        List the calling tenant's strategy on the leaderboard. Returns None if the
        strategy does not belong to this tenant (ownership enforced in the INSERT's
        WHERE EXISTS). Re-publishing updates the listing's metadata in place.
        """
        return await self.fetchrow(
            """
            INSERT INTO public_strategies
                (strategy_id, creator_tenant_id, creator_user_id, title, description, management_fee_bps)
            SELECT $1, $2, $3, $4, $5, $6
            WHERE EXISTS (
                SELECT 1 FROM strategies WHERE id = $1 AND tenant_id = $2
            )
            ON CONFLICT (strategy_id) DO UPDATE SET
                title              = EXCLUDED.title,
                description        = EXCLUDED.description,
                management_fee_bps = EXCLUDED.management_fee_bps,
                is_listed          = TRUE,
                updated_at         = now()
            RETURNING *
            """,
            strategy_id,
            self.tenant_id,
            creator_user_id,
            title,
            description,
            management_fee_bps,
        )

    # ── Subscribe (tenant-scoped write) ────────────────────────────────────────
    async def subscribe(
        self,
        public_strategy_id: UUID,
        subscriber_user_id: UUID,
        allocated_capital: float,
    ) -> asyncpg.Record:
        """
        Copy a published strategy with a capital allocation. Atomic: upserts the
        subscription and keeps public_strategies.subscriber_count consistent (only
        incremented when a NEW active subscription is created). Raises ValueError
        if the listing is missing or the caller is its creator (no self-copy).
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                pub = await conn.fetchrow(
                    "SELECT id, creator_tenant_id FROM public_strategies WHERE id = $1 AND is_listed FOR UPDATE",
                    public_strategy_id,
                )
                if pub is None:
                    raise ValueError("Public strategy not found or no longer listed.")
                if pub["creator_tenant_id"] == self.tenant_id:
                    raise ValueError("You cannot copy your own published strategy.")

                existing = await conn.fetchrow(
                    """
                    SELECT id, is_active FROM strategy_subscriptions
                    WHERE public_strategy_id = $1 AND subscriber_tenant_id = $2
                    """,
                    public_strategy_id,
                    self.tenant_id,
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO strategy_subscriptions
                        (public_strategy_id, subscriber_tenant_id, subscriber_user_id, allocated_capital)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (public_strategy_id, subscriber_tenant_id) DO UPDATE SET
                        allocated_capital = EXCLUDED.allocated_capital,
                        subscriber_user_id = EXCLUDED.subscriber_user_id,
                        is_active = TRUE,
                        updated_at = now()
                    RETURNING *
                    """,
                    public_strategy_id,
                    self.tenant_id,
                    subscriber_user_id,
                    allocated_capital,
                )
                # Count only transitions into an active subscription.
                if existing is None or not existing["is_active"]:
                    await conn.execute(
                        "UPDATE public_strategies SET subscriber_count = subscriber_count + 1, updated_at = now() WHERE id = $1",
                        public_strategy_id,
                    )
                return row

    async def unsubscribe(self, public_strategy_id: UUID) -> bool:
        """Deactivate the caller's subscription. Returns True if one was active."""
        async with self.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE strategy_subscriptions
                    SET is_active = FALSE, updated_at = now()
                    WHERE public_strategy_id = $1 AND subscriber_tenant_id = $2 AND is_active
                    RETURNING id
                    """,
                    public_strategy_id,
                    self.tenant_id,
                )
                if row is None:
                    return False
                await conn.execute(
                    "UPDATE public_strategies SET subscriber_count = GREATEST(subscriber_count - 1, 0), updated_at = now() WHERE id = $1",
                    public_strategy_id,
                )
                return True

    async def list_subscriptions(self) -> list[asyncpg.Record]:
        """The calling tenant's active copy subscriptions (with listing metadata)."""
        return await self.fetch(
            """
            SELECT ss.id, ss.public_strategy_id, ss.allocated_capital, ss.created_at,
                   ps.title, ps.strategy_id, ps.management_fee_bps, ps.subscriber_count
            FROM strategy_subscriptions ss
            JOIN public_strategies ps ON ps.id = ss.public_strategy_id
            WHERE ss.subscriber_tenant_id = $1 AND ss.is_active
            ORDER BY ss.created_at DESC
            """,
            self.tenant_id,
        )
