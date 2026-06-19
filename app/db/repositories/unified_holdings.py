from datetime import date

import asyncpg

from app.db.base_repo import BaseRepo


class UnifiedHoldingsRepo(BaseRepo):
    """Tenant-scoped access to consolidated multi-broker holdings."""

    async def replace_all(
        self, holdings: list[dict], statement_date: date | None
    ) -> int:
        """
        Replace the tenant's entire holdings set with a freshly-parsed CAS.
        A CAS is a full account statement, so an upload supersedes the previous
        snapshot — delete + insert run in one transaction to stay atomic.
        Returns the number of rows inserted.
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM unified_holdings WHERE tenant_id = $1",
                    self.tenant_id,
                )
                if not holdings:
                    return 0
                await conn.executemany(
                    """
                    INSERT INTO unified_holdings (
                        tenant_id, isin, symbol, name, asset_class, broker,
                        quantity, avg_cost, current_price, current_value, statement_date
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    [
                        (
                            self.tenant_id,
                            h["isin"],
                            h["symbol"],
                            h["name"],
                            h["asset_class"],
                            h["broker"],
                            h["quantity"],
                            h["avg_cost"],
                            h["current_price"],
                            h["current_value"],
                            statement_date,
                        )
                        for h in holdings
                    ],
                )
        return len(holdings)

    async def list_all(self) -> list[asyncpg.Record]:
        return await self.fetch(
            """
            SELECT * FROM unified_holdings
            WHERE tenant_id = $1
            ORDER BY current_value DESC
            """,
            self.tenant_id,
        )
