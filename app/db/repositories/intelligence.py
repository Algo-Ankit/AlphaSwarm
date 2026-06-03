"""
Repositories for the intelligence layer — forecasts and news_items.
Not tenant-scoped: market intelligence data is shared across all tenants.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import asyncpg


class ForecastRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_latest(
        self, symbol: str, exchange: str, horizon_days: int = 5
    ) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, symbol, exchange, generated_at, horizon_days,
                       model, mae, mape, forecast_json
                FROM forecasts
                WHERE symbol = $1 AND exchange = $2 AND horizon_days = $3
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                symbol.upper(),
                exchange.upper(),
                horizon_days,
            )

    async def upsert(
        self,
        symbol: str,
        exchange: str,
        horizon_days: int,
        model: str,
        mae: Decimal | None,
        mape: Decimal | None,
        forecast_json: list[dict],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO forecasts
                    (symbol, exchange, horizon_days, model, mae, mape, forecast_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                symbol.upper(),
                exchange.upper(),
                horizon_days,
                model,
                mae,
                mape,
                json.dumps(forecast_json),
            )


class NewsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_symbol(
        self, symbol: str, days: int = 7, limit: int = 20
    ) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, symbol, headline, summary, source, url,
                       sentiment, category, published_at, fetched_at
                FROM news_items
                WHERE symbol = $1
                  AND published_at >= NOW() - ($2 || ' days')::interval
                ORDER BY published_at DESC
                LIMIT $3
                """,
                symbol.upper(),
                str(days),
                limit,
            )

    async def latest_fetch_time(self, symbol: str) -> datetime | None:
        async with self._pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT MAX(fetched_at) FROM news_items WHERE symbol = $1",
                symbol.upper(),
            )
        if val is not None and val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val

    async def bulk_upsert(self, items: list[dict]) -> None:
        """Insert news items, skipping exact headline+published_at duplicates."""
        if not items:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO news_items
                    (symbol, headline, summary, source, url, sentiment, category, published_at)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8
                WHERE NOT EXISTS (
                    SELECT 1 FROM news_items
                    WHERE symbol = $1 AND headline = $2 AND published_at = $8
                )
                """,
                [
                    (
                        it["symbol"].upper(),
                        it["headline"],
                        it.get("summary"),
                        it["source"],
                        it.get("url"),
                        it.get("sentiment"),
                        it.get("category"),
                        it["published_at"],
                    )
                    for it in items
                ],
            )

    async def get_active_symbols(self) -> list[tuple[str, str]]:
        """Return distinct (symbol, exchange) pairs with currently running strategies."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT unnest(s.symbols) AS symbol, s.exchange
                FROM strategy_runs sr
                JOIN strategies s ON s.id = sr.strategy_id
                WHERE sr.status = 'running'
                """
            )
        return [(r["symbol"].upper(), r["exchange"].upper()) for r in rows]
