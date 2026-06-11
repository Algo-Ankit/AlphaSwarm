from uuid import UUID

import asyncpg

from app.db.base_repo import BaseRepo


class BacktestRepo(BaseRepo):
    """Persisted backtest runs — tenant-isolated."""

    async def create(
        self,
        strategy_id: UUID,
        version_id: UUID | None,
        symbol: str,
        exchange: str,
        timeframe: str,
        start_date,
        end_date,
        initial_capital: float,
        final_equity: float,
        total_return_pct: float,
        sharpe_ratio: float,
        max_drawdown_pct: float,
        win_rate_pct: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        equity_curve: list[float],
        trades: list[dict],
    ) -> asyncpg.Record:
        import json as _json

        return await self.fetchrow(
            """
            INSERT INTO backtest_results
                (strategy_id, version_id, tenant_id, symbol, exchange, timeframe,
                 start_date, end_date, initial_capital, final_equity,
                 total_return_pct, sharpe_ratio, max_drawdown_pct, win_rate_pct,
                 total_trades, winning_trades, losing_trades,
                 equity_curve_json, trades_json)
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                   $11, $12, $13, $14, $15, $16, $17, $18::jsonb, $19::jsonb
            WHERE EXISTS (
                SELECT 1 FROM strategies WHERE id = $1 AND tenant_id = $3
            )
            RETURNING *
            """,
            strategy_id, version_id, self.tenant_id, symbol, exchange, timeframe,
            start_date, end_date, initial_capital, final_equity,
            total_return_pct, sharpe_ratio, max_drawdown_pct, win_rate_pct,
            total_trades, winning_trades, losing_trades,
            _json.dumps(equity_curve), _json.dumps(trades),
        )

    async def get_latest(self, strategy_id: UUID) -> asyncpg.Record | None:
        return await self.fetchrow(
            """
            SELECT b.*
            FROM backtest_results b
            JOIN strategies s ON s.id = b.strategy_id
            WHERE b.strategy_id = $1 AND s.tenant_id = $2
            ORDER BY b.created_at DESC
            LIMIT 1
            """,
            strategy_id, self.tenant_id,
        )
