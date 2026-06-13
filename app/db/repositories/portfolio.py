import asyncpg

from app.db.base_repo import BaseRepo


class PortfolioRepo(BaseRepo):
    """Tenant-scoped read access to portfolio_snapshots."""

    async def latest(self) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT * FROM portfolio_snapshots
            WHERE tenant_id = $1
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            self.tenant_id,
        )

    async def history(self, limit: int = 200) -> list[asyncpg.Record]:
        """Most recent `limit` snapshots, returned oldest→newest for charting."""
        rows = await self.fetch(
            """
            SELECT snapshot_time, total_equity, open_pnl, realized_pnl_today, active_strategies
            FROM portfolio_snapshots
            WHERE tenant_id = $1
            ORDER BY snapshot_time DESC
            LIMIT $2
            """,
            self.tenant_id, limit,
        )
        return list(reversed(rows))
