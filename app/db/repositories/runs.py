from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class RunRepo(BaseRepo):
    """Strategy runs — tenant-isolated."""

    async def create(
        self,
        strategy_id: UUID,
        version_id: UUID | None,
        dry_run: bool,
    ) -> asyncpg.Record:
        return await self.fetchrow(
            """
            INSERT INTO strategy_runs
                (tenant_id, strategy_id, version_id, dry_run, status)
            VALUES ($1, $2, $3, $4, 'queued')
            RETURNING *
            """,
            self.tenant_id, strategy_id, version_id, dry_run,
        )

    async def mark_dispatched(self, run_id: UUID, celery_task_id: str) -> None:
        await self.execute(
            """
            UPDATE strategy_runs
            SET celery_task_id = $1, status = 'queued', updated_at = now()
            WHERE id = $2 AND tenant_id = $3
            """,
            celery_task_id, run_id, self.tenant_id,
        )

    async def mark_failed(self, run_id: UUID, error: str) -> None:
        await self.execute(
            """
            UPDATE strategy_runs
            SET status = 'failed', error = $1, ended_at = now(), updated_at = now()
            WHERE id = $2 AND tenant_id = $3
            """,
            error, run_id, self.tenant_id,
        )

    async def get_by_id(self, run_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            "SELECT * FROM strategy_runs WHERE id = $1 AND tenant_id = $2",
            run_id, self.tenant_id,
        )

    async def list_by_strategy(self, strategy_id: UUID) -> list[asyncpg.Record]:
        return await self.fetch(
            """
            SELECT * FROM strategy_runs
            WHERE strategy_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT 50
            """,
            strategy_id, self.tenant_id,
        )
