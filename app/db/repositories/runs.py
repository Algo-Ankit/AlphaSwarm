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
        # Defense-in-depth: INSERT only if strategy_id belongs to this tenant,
        # preventing IDOR even if the API layer check is bypassed.
        row = await self.fetchrow(
            """
            INSERT INTO strategy_runs
                (tenant_id, strategy_id, version_id, dry_run, status)
            SELECT $1, $2, $3, $4, 'queued'
            WHERE EXISTS (
                SELECT 1 FROM strategies WHERE id = $2 AND tenant_id = $1
            )
            RETURNING *
            """,
            self.tenant_id, strategy_id, version_id, dry_run,
        )
        if row is None:
            raise ValueError(
                f"Strategy {strategy_id} not found or does not belong to tenant {self.tenant_id}"
            )
        return row

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

    async def mark_running(self, run_id: UUID) -> None:
        await self.execute(
            """
            UPDATE strategy_runs
            SET status = 'running', started_at = now(), updated_at = now()
            WHERE id = $1 AND tenant_id = $2
            """,
            run_id, self.tenant_id,
        )

    async def touch(self, run_id: UUID) -> None:
        """Heartbeat — bump updated_at so the stale-run reaper doesn't kill a
        still-working run. Only affects rows currently in 'running' status."""
        await self.execute(
            """
            UPDATE strategy_runs
            SET updated_at = now()
            WHERE id = $1 AND tenant_id = $2 AND status = 'running'
            """,
            run_id, self.tenant_id,
        )

    async def mark_completed(self, run_id: UUID, result: dict) -> None:
        import json
        await self.execute(
            """
            UPDATE strategy_runs
            SET status = 'completed', result = $1, ended_at = now(), updated_at = now()
            WHERE id = $2 AND tenant_id = $3
            """,
            json.dumps(result), run_id, self.tenant_id,
        )

    async def mark_crashed(self, run_id: UUID, reason: str) -> None:
        await self.execute(
            """
            UPDATE strategy_runs
            SET status = 'failed', error = $1, ended_at = now(), updated_at = now()
            WHERE id = $2 AND tenant_id = $3
            """,
            reason, run_id, self.tenant_id,
        )

    async def get_stale_running_runs(self, stale_seconds: int = 90) -> list[asyncpg.Record]:
        """Returns runs stuck in 'running' status with no update for stale_seconds."""
        return await self.fetch(
            """
            SELECT * FROM strategy_runs
            WHERE tenant_id = $1
              AND status = 'running'
              AND updated_at < now() - ($2 * INTERVAL '1 second')
            """,
            self.tenant_id, stale_seconds,
        )
