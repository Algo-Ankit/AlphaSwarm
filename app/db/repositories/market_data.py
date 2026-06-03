from datetime import datetime, timezone

import asyncpg

from app.domain.market_data import Bar


class MarketDataRepo:
    """Not tenant-scoped — market data is shared across all tenants."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[asyncpg.Record]:
        where = ["symbol = $1", "exchange = $2", "timeframe = $3"]
        params: list = [symbol.upper(), exchange.upper(), timeframe]
        i = 4
        if start:
            where.append(f"bar_time >= ${i}")
            params.append(start)
            i += 1
        if end:
            where.append(f"bar_time <= ${i}")
            params.append(end)
            i += 1
        params.append(limit)
        sql = f"""
            SELECT symbol, exchange, timeframe, bar_time, open, high, low, close, volume
            FROM market_data_cache
            WHERE {' AND '.join(where)}
            ORDER BY bar_time DESC
            LIMIT ${i}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return list(reversed(rows))  # oldest-first

    async def latest_bar_time(
        self, symbol: str, exchange: str, timeframe: str
    ) -> datetime | None:
        async with self._pool.acquire() as conn:
            val = await conn.fetchval(
                """
                SELECT MAX(bar_time) FROM market_data_cache
                WHERE symbol = $1 AND exchange = $2 AND timeframe = $3
                """,
                symbol.upper(), exchange.upper(), timeframe,
            )
        if val is not None and val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val

    async def bulk_upsert(self, bars: list[Bar]) -> None:
        if not bars:
            return
        rows = [
            (
                b.symbol.upper(), b.exchange.upper(), b.timeframe, b.timestamp,
                b.open, b.high, b.low, b.close, b.volume,
            )
            for b in bars
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO market_data_cache
                    (symbol, exchange, timeframe, bar_time, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol, exchange, timeframe, bar_time) DO UPDATE SET
                    open   = EXCLUDED.open,
                    high   = EXCLUDED.high,
                    low    = EXCLUDED.low,
                    close  = EXCLUDED.close,
                    volume = EXCLUDED.volume
                """,
                rows,
            )
