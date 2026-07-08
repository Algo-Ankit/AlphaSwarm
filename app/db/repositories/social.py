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
                ps.fork_count,
                ps.forked_from_public_strategy_id,
                ps.is_verified,
                ps.created_at,
                ps.published_at,
                ps.oos_total_return_pct,
                ps.oos_annualized_return_pct AS oos_cagr_pct,
                ps.oos_sharpe_ratio,
                ps.oos_max_drawdown_pct,
                ps.oos_total_trades,
                ps.oos_computed_at,
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
    async def count_backtests(self, strategy_id: UUID) -> int:
        """How many backtest runs this strategy has on-platform (publish gate)."""
        val = await self.fetchval(
            "SELECT count(*) FROM backtest_results WHERE strategy_id = $1 AND tenant_id = $2",
            strategy_id,
            self.tenant_id,
        )
        return int(val or 0)

    async def publish(
        self,
        strategy_id: UUID,
        creator_user_id: UUID,
        title: str,
        description: str,
        management_fee_bps: int,
    ) -> asyncpg.Record | None:
        """
        List the calling tenant's strategy on the leaderboard, pinning the exact
        immutable version that is current at publish time (published_version_id) —
        what subscribers copy and forkers fork is a frozen snapshot, not a moving
        head. Returns None if the strategy does not belong to this tenant. If this
        strategy was itself forked, the lineage link + parent fork_count are
        carried onto the listing so the graph is complete.

        Re-publishing updates metadata AND re-pins to the new current version.
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                strat = await conn.fetchrow(
                    """
                    SELECT current_version_id, forked_from_public_strategy_id
                    FROM strategies WHERE id = $1 AND tenant_id = $2
                    """,
                    strategy_id,
                    self.tenant_id,
                )
                if strat is None:
                    return None

                row = await conn.fetchrow(
                    """
                    INSERT INTO public_strategies
                        (strategy_id, creator_tenant_id, creator_user_id, title,
                         description, management_fee_bps, published_version_id,
                         forked_from_public_strategy_id, published_at, oos_start_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), now())
                    ON CONFLICT (strategy_id) DO UPDATE SET
                        title                = EXCLUDED.title,
                        description          = EXCLUDED.description,
                        management_fee_bps   = EXCLUDED.management_fee_bps,
                        published_version_id = EXCLUDED.published_version_id,
                        is_listed            = TRUE,
                        published_at         = now(),
                        -- Re-pinning a new version resets the out-of-sample boundary
                        -- and invalidates the stale OOS scorecard until recomputed.
                        oos_start_date       = now(),
                        oos_computed_at      = NULL,
                        updated_at           = now()
                    RETURNING *, (xmax = 0) AS _inserted
                    """,
                    strategy_id,
                    self.tenant_id,
                    creator_user_id,
                    title,
                    description,
                    management_fee_bps,
                    strat["current_version_id"],
                    strat["forked_from_public_strategy_id"],
                )
                # First-time publish of a forked strategy: credit the parent listing.
                if row["_inserted"] and strat["forked_from_public_strategy_id"] is not None:
                    await conn.execute(
                        "UPDATE public_strategies SET fork_count = fork_count + 1 "
                        "WHERE id = $1",
                        strat["forked_from_public_strategy_id"],
                    )
                return row

    # ── Fork (cross-tenant read of a listing → tenant-scoped strategy write) ────
    async def fork(self, public_strategy_id: UUID, forker_user_id: UUID) -> asyncpg.Record | None:
        """
        Copy a published strategy's pinned immutable version into a NEW private
        strategy owned by the calling tenant, recording the lineage link. Returns
        the new strategy row (with generated_logic), or None if the listing is
        missing. Cannot fork your own listing. Increments the source fork_count
        immediately — the fork happened whether or not it is ever re-published.
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                src = await conn.fetchrow(
                    """
                    SELECT ps.id, ps.creator_tenant_id, ps.title, ps.published_version_id,
                           s.symbols, s.exchange, s.timeframe, s.risk_config, s.prompt,
                           s.creation_mode
                    FROM public_strategies ps
                    JOIN strategies s ON s.id = ps.strategy_id
                    WHERE ps.id = $1 AND ps.is_listed
                    FOR UPDATE OF ps
                    """,
                    public_strategy_id,
                )
                if src is None:
                    raise ValueError("Public strategy not found or no longer listed.")
                if src["creator_tenant_id"] == self.tenant_id:
                    raise ValueError("You cannot fork your own published strategy.")

                # Snapshot the exact published version's code/explanation/prompt.
                ver = await conn.fetchrow(
                    """
                    SELECT generated_logic, explanation, prompt_snapshot
                    FROM strategy_versions WHERE id = $1
                    """,
                    src["published_version_id"],
                )
                if ver is None:
                    raise ValueError("Published version snapshot is unavailable.")

                new_strat = await conn.fetchrow(
                    """
                    INSERT INTO strategies
                        (tenant_id, owner_user_id, name, prompt, symbols, exchange,
                         timeframe, creation_mode, risk_config, forked_from_public_strategy_id)
                    VALUES ($1, $2, $3, $4, $5::text[], $6, $7, $8, $9::jsonb, $10)
                    RETURNING *
                    """,
                    self.tenant_id,
                    forker_user_id,
                    f"{src['title']} (fork)",
                    src["prompt"],
                    list(src["symbols"]),
                    src["exchange"],
                    src["timeframe"],
                    src["creation_mode"],
                    src["risk_config"],
                    public_strategy_id,
                )
                version = await conn.fetchrow(
                    """
                    INSERT INTO strategy_versions
                        (strategy_id, version_number, generated_logic, explanation,
                         prompt_snapshot, created_by)
                    VALUES ($1, 1, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    new_strat["id"],
                    ver["generated_logic"],
                    ver["explanation"],
                    ver["prompt_snapshot"],
                    forker_user_id,
                )
                await conn.execute(
                    "UPDATE strategies SET current_version_id = $1 WHERE id = $2",
                    version["id"],
                    new_strat["id"],
                )
                await conn.execute(
                    "UPDATE public_strategies SET fork_count = fork_count + 1, updated_at = now() "
                    "WHERE id = $1",
                    public_strategy_id,
                )
                return await conn.fetchrow(
                    """
                    SELECT s.*, sv.generated_logic, sv.explanation, sv.version_number
                    FROM strategies s
                    JOIN strategy_versions sv ON sv.id = s.current_version_id
                    WHERE s.id = $1
                    """,
                    new_strat["id"],
                )

    async def lineage(self, public_strategy_id: UUID) -> dict:
        """
        The fork graph around a listing: its ancestor chain (walking up the
        forked_from links, root last) and its direct children. Cross-tenant read.
        """
        ancestors = await self.fetch(
            """
            WITH RECURSIVE chain AS (
                SELECT p.id, p.title, p.forked_from_public_strategy_id, 0 AS depth
                FROM public_strategies p WHERE p.id = $1
                UNION ALL
                SELECT p.id, p.title, p.forked_from_public_strategy_id, c.depth + 1
                FROM public_strategies p
                JOIN chain c ON p.id = c.forked_from_public_strategy_id
            )
            SELECT id, title, depth FROM chain WHERE depth > 0 ORDER BY depth
            """,
            public_strategy_id,
        )
        children = await self.fetch(
            """
            SELECT ps.id, ps.title, ps.subscriber_count, ps.fork_count, t.name AS creator_name,
                   bt.sharpe_ratio, bt.annualized_return_pct AS cagr_pct
            FROM public_strategies ps
            JOIN tenants t ON t.id = ps.creator_tenant_id
            LEFT JOIN LATERAL (
                SELECT b.sharpe_ratio, b.annualized_return_pct
                FROM backtest_results b
                WHERE b.strategy_id = ps.strategy_id
                ORDER BY b.created_at DESC LIMIT 1
            ) bt ON TRUE
            WHERE ps.forked_from_public_strategy_id = $1 AND ps.is_listed
            ORDER BY COALESCE(bt.sharpe_ratio, 0) DESC
            """,
            public_strategy_id,
        )
        return {"ancestors": ancestors, "children": children}

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
