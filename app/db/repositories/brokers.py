from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class BrokerRepo(BaseRepo):

    async def upsert(
        self,
        broker: str,
        key_encrypted: str,
        secret_encrypted: str,
        base_url: str,
        is_paper: bool,
    ) -> asyncpg.Record:
        return await self.fetchrow(
            """
            INSERT INTO broker_connections
                (tenant_id, broker, key_encrypted, secret_encrypted, base_url, is_paper)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (tenant_id, broker)
            DO UPDATE SET
                key_encrypted    = EXCLUDED.key_encrypted,
                secret_encrypted = EXCLUDED.secret_encrypted,
                base_url         = EXCLUDED.base_url,
                is_paper         = EXCLUDED.is_paper,
                updated_at       = now()
            RETURNING *
            """,
            self.tenant_id, broker, key_encrypted, secret_encrypted, base_url, is_paper,
        )

    async def upsert_oauth(
        self,
        broker: str,
        key_encrypted: str,
        secret_encrypted: str,
        access_token: str | None,
        refresh_token: str | None,
        token_expires_at: datetime | None,
        is_paper: bool = False,
        base_url: str = "",
    ) -> asyncpg.Record:
        """Upsert a broker connection that uses OAuth tokens instead of static API keys."""
        return await self.fetchrow(
            """
            INSERT INTO broker_connections
                (tenant_id, broker, key_encrypted, secret_encrypted, base_url, is_paper,
                 access_token, refresh_token, token_expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (tenant_id, broker)
            DO UPDATE SET
                key_encrypted    = EXCLUDED.key_encrypted,
                secret_encrypted = EXCLUDED.secret_encrypted,
                base_url         = EXCLUDED.base_url,
                is_paper         = EXCLUDED.is_paper,
                access_token     = EXCLUDED.access_token,
                refresh_token    = EXCLUDED.refresh_token,
                token_expires_at = EXCLUDED.token_expires_at,
                updated_at       = now()
            RETURNING *
            """,
            self.tenant_id, broker, key_encrypted, secret_encrypted, base_url, is_paper,
            access_token, refresh_token, token_expires_at,
        )

    async def update_oauth_tokens(
        self,
        broker: str,
        access_token: str,
        refresh_token: str | None,
        token_expires_at: datetime | None,
    ) -> None:
        """Rotate access/refresh tokens without touching key_encrypted."""
        await self.execute(
            """
            UPDATE broker_connections
            SET access_token     = $1,
                refresh_token    = COALESCE($2, refresh_token),
                token_expires_at = $3,
                updated_at       = now()
            WHERE tenant_id = $4 AND broker = $5
            """,
            access_token, refresh_token, token_expires_at, self.tenant_id, broker,
        )

    async def set_oauth_state(self, broker: str, state: str) -> None:
        """Store CSRF state token before redirecting user to broker OAuth page."""
        await self.execute(
            """
            INSERT INTO broker_connections
                (tenant_id, broker, key_encrypted, secret_encrypted, oauth_state)
            VALUES ($1, $2, '', '', $3)
            ON CONFLICT (tenant_id, broker)
            DO UPDATE SET oauth_state = EXCLUDED.oauth_state, updated_at = now()
            """,
            self.tenant_id, broker, state,
        )

    async def get_by_broker(self, broker: str) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT * FROM broker_connections
            WHERE tenant_id = $1 AND broker = $2 AND is_active = true
            """,
            self.tenant_id, broker,
        )

    async def get_all(self) -> list[asyncpg.Record]:
        return await self.fetch(
            """
            SELECT * FROM broker_connections
            WHERE tenant_id = $1 AND is_active = true
            ORDER BY created_at
            """,
            self.tenant_id,
        )

    async def get_by_id(self, connection_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT * FROM broker_connections
            WHERE id = $1 AND tenant_id = $2 AND is_active = true
            """,
            connection_id, self.tenant_id,
        )

    async def delete(self, connection_id: UUID) -> None:
        await self.execute(
            "DELETE FROM broker_connections WHERE id = $1 AND tenant_id = $2",
            connection_id, self.tenant_id,
        )
