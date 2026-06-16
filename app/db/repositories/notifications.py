from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class NotificationRepo(BaseRepo):
    """
    Tenant-scoped notifications. user_id may be NULL (tenant-wide), so reads
    return rows addressed to this user OR to the whole tenant.
    """

    async def create(
        self,
        user_id: UUID | None,
        type: str,
        title: str,
        body: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
    ) -> asyncpg.Record:
        return await self.fetchrow(
            """
            INSERT INTO notifications (tenant_id, user_id, type, title, body, entity_type, entity_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            self.tenant_id, user_id, type, title, body, entity_type, entity_id,
        )

    async def get_by_id(self, notif_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT * FROM notifications WHERE id = $1 AND tenant_id = $2",
            notif_id, self.tenant_id,
        )

    async def approve(self, notif_id: UUID, user_id: UUID) -> str:
        return await self.execute(
            """
            UPDATE notifications
            SET is_read = TRUE, approved_at = now()
            WHERE id = $1 AND tenant_id = $2 AND (user_id = $3 OR user_id IS NULL)
            """,
            notif_id, self.tenant_id, user_id,
        )

    async def list(
        self, user_id: UUID, *, unread_only: bool = False, limit: int = 50
    ) -> list[asyncpg.Record]:
        clause = "AND is_read = FALSE" if unread_only else ""
        return await self.fetch(
            f"""
            SELECT * FROM notifications
            WHERE tenant_id = $1
              AND (user_id = $2 OR user_id IS NULL)
              {clause}
            ORDER BY created_at DESC
            LIMIT $3
            """,
            self.tenant_id, user_id, limit,
        )

    async def unread_count(self, user_id: UUID) -> int:
        val = await self.fetchval(
            """
            SELECT COUNT(*) FROM notifications
            WHERE tenant_id = $1
              AND (user_id = $2 OR user_id IS NULL)
              AND is_read = FALSE
            """,
            self.tenant_id, user_id,
        )
        return int(val or 0)

    async def mark_read(self, notif_id: UUID, user_id: UUID) -> str:
        return await self.execute(
            """
            UPDATE notifications SET is_read = TRUE
            WHERE id = $1 AND tenant_id = $2 AND (user_id = $3 OR user_id IS NULL)
            """,
            notif_id, self.tenant_id, user_id,
        )

    async def mark_all_read(self, user_id: UUID) -> None:
        await self.execute(
            """
            UPDATE notifications SET is_read = TRUE
            WHERE tenant_id = $1 AND (user_id = $2 OR user_id IS NULL) AND is_read = FALSE
            """,
            self.tenant_id, user_id,
        )
