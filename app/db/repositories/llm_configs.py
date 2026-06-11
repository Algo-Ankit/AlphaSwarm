from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class LLMConfigRepo(BaseRepo):

    async def create(
        self,
        owner_user_id: UUID,
        label: str,
        provider: str,
        base_url: str,
        key_encrypted: str,
        model: str,
    ) -> asyncpg.Record:
        return await self.fetchrow(
            """
            INSERT INTO llm_configs
                (tenant_id, owner_user_id, label, provider, base_url, key_encrypted, model)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            self.tenant_id, owner_user_id, label, provider, base_url, key_encrypted, model,
        )

    async def get_all(self) -> list[asyncpg.Record]:
        return await self.fetch(
            """
            SELECT * FROM llm_configs
            WHERE tenant_id = $1 AND is_active = TRUE
            ORDER BY created_at
            """,
            self.tenant_id,
        )

    async def get_by_id(self, config_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT * FROM llm_configs
            WHERE id = $1 AND tenant_id = $2 AND is_active = TRUE
            """,
            config_id, self.tenant_id,
        )

    async def delete(self, config_id: UUID) -> None:
        await self.execute(
            "DELETE FROM llm_configs WHERE id = $1 AND tenant_id = $2",
            config_id, self.tenant_id,
        )
