from typing import Any
from uuid import UUID

import asyncpg


class BaseRepo:
    """
    Base for all tenant-scoped repositories.
    tenant_id is stored at construction time — every repo method must use it in WHERE clauses.
    No query may omit the tenant_id filter. This is enforced by convention: every public method
    receives tenant_id from self.tenant_id, never from the caller.
    """

    def __init__(self, pool: asyncpg.Pool, tenant_id: UUID) -> None:
        self._pool = pool
        self.tenant_id = tenant_id

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    def acquire(self):
        return self._pool.acquire()
