import hashlib
from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class TenantRepo:
    """Auth-scope repo — not tenant-filtered (used during registration)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, name: str, plan: str = "founding_member") -> asyncpg.Record:
        return await self._pool.fetchrow(
            "INSERT INTO tenants (name, plan) VALUES ($1, $2) RETURNING *",
            name, plan,
        )

    async def get_by_id(self, tenant_id: UUID) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT * FROM tenants WHERE id = $1",
            tenant_id,
        )


class AuthUserRepo:
    """
    Auth-scope user repo — no tenant_id filter.
    Only used during register/login before tenant is established.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        tenant_id: UUID,
        email: str,
        password_hash: str,
        display_name: str,
        role: str = "owner",
    ) -> asyncpg.Record:
        return await self._pool.fetchrow(
            """
            INSERT INTO users (tenant_id, email, password_hash, display_name, role)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            tenant_id, email, password_hash, display_name, role,
        )

    async def get_by_email(self, email: str) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT * FROM users WHERE email = $1 AND is_active = true LIMIT 1",
            email,
        )

    async def get_by_id(self, user_id: UUID) -> asyncpg.Record | None:
        return await self._pool.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND is_active = true",
            user_id,
        )


class RefreshTokenRepo:

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    async def create(
        self,
        user_id: UUID,
        raw_token: str,
        expires_at: datetime,
    ) -> asyncpg.Record:
        token_hash = self.hash_token(raw_token)
        return await self._pool.fetchrow(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            user_id, token_hash, expires_at,
        )

    async def get_by_raw_token(self, raw_token: str) -> asyncpg.Record | None:
        token_hash = self.hash_token(raw_token)
        return await self._pool.fetchrow(
            """
            SELECT rt.*, u.tenant_id, u.email, u.role
            FROM refresh_tokens rt
            JOIN users u ON u.id = rt.user_id
            WHERE rt.token_hash = $1 AND rt.expires_at > now()
            """,
            token_hash,
        )

    async def delete_by_raw_token(self, raw_token: str) -> None:
        token_hash = self.hash_token(raw_token)
        await self._pool.execute(
            "DELETE FROM refresh_tokens WHERE token_hash = $1",
            token_hash,
        )

    async def delete_all_for_user(self, user_id: UUID) -> None:
        await self._pool.execute(
            "DELETE FROM refresh_tokens WHERE user_id = $1",
            user_id,
        )


class UserRepo(BaseRepo):
    """Tenant-scoped user queries."""

    async def get_by_id(self, user_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2 AND is_active = true",
            user_id, self.tenant_id,
        )

    async def list_users(self) -> list[asyncpg.Record]:
        return await self.fetch(
            """
            SELECT id, email, display_name, role, created_at
            FROM users WHERE tenant_id = $1 AND is_active = true
            """,
            self.tenant_id,
        )
