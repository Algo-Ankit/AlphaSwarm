from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class StrategyRepo(BaseRepo):
    """All strategy CRUD — tenant-isolated at every query."""

    async def create(
        self,
        owner_user_id: UUID,
        name: str,
        prompt: str,
        symbols: list[str],
        exchange: str,
        timeframe: str,
        creation_mode: str,
        risk_config: dict,
        generated_logic: str,
    ) -> asyncpg.Record:
        async with self.acquire() as conn:
            async with conn.transaction():
                strategy = await conn.fetchrow(
                    """
                    INSERT INTO strategies
                        (tenant_id, owner_user_id, name, prompt, symbols, exchange,
                         timeframe, creation_mode, risk_config)
                    VALUES ($1, $2, $3, $4, $5::text[], $6, $7, $8, $9::jsonb)
                    RETURNING *
                    """,
                    self.tenant_id, owner_user_id, name, prompt,
                    symbols, exchange, timeframe, creation_mode,
                    risk_config,
                )
                version = await conn.fetchrow(
                    """
                    INSERT INTO strategy_versions
                        (strategy_id, version_number, generated_logic, prompt_snapshot, created_by)
                    VALUES ($1, 1, $2, $3, $4)
                    RETURNING *
                    """,
                    strategy["id"], generated_logic, prompt, owner_user_id,
                )
                await conn.execute(
                    "UPDATE strategies SET current_version_id = $1 WHERE id = $2",
                    version["id"], strategy["id"],
                )
                return await conn.fetchrow(
                    """
                    SELECT s.*, sv.generated_logic, sv.version_number
                    FROM strategies s
                    JOIN strategy_versions sv ON sv.id = s.current_version_id
                    WHERE s.id = $1
                    """,
                    strategy["id"],
                )

    async def get_by_id(self, strategy_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT s.*, sv.generated_logic, sv.version_number
            FROM strategies s
            LEFT JOIN strategy_versions sv ON sv.id = s.current_version_id
            WHERE s.id = $1 AND s.tenant_id = $2
            """,
            strategy_id, self.tenant_id,
        )

    async def list_all(self, status: str | None = None) -> list[asyncpg.Record]:
        if status:
            return await self.fetch(
                """
                SELECT s.*, sv.generated_logic, sv.version_number
                FROM strategies s
                LEFT JOIN strategy_versions sv ON sv.id = s.current_version_id
                WHERE s.tenant_id = $1 AND s.status = $2
                ORDER BY s.created_at DESC
                """,
                self.tenant_id, status,
            )
        return await self.fetch(
            """
            SELECT s.*, sv.generated_logic, sv.version_number
            FROM strategies s
            LEFT JOIN strategy_versions sv ON sv.id = s.current_version_id
            WHERE s.tenant_id = $1
            ORDER BY s.created_at DESC
            """,
            self.tenant_id,
        )

    async def update_status(self, strategy_id: UUID, new_status: str) -> None:
        await self.execute(
            """
            UPDATE strategies SET status = $1, updated_at = now()
            WHERE id = $2 AND tenant_id = $3
            """,
            new_status, strategy_id, self.tenant_id,
        )

    async def get_current_version_id(self, strategy_id: UUID) -> UUID | None:
        return await self.fetchval(
            "SELECT current_version_id FROM strategies WHERE id = $1 AND tenant_id = $2",
            strategy_id, self.tenant_id,
        )
