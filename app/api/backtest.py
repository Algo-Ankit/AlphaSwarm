"""
Backtest API — POST /v1/strategies/{id}/backtest
Runs a bar-by-bar simulation of the strategy's current generated_logic against historical data.
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.strategies import StrategyRepo
from app.domain.models import BacktestRequest, BacktestResponse, BacktestTradeRecord, BacktestMetricsModel

router = APIRouter(prefix="/v1", tags=["backtest"])


@router.post(
    "/strategies/{strategy_id}/backtest",
    response_model=BacktestResponse,
    status_code=status.HTTP_200_OK,
)
async def run_strategy_backtest(
    strategy_id: UUID,
    request: BacktestRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> BacktestResponse:
    repo = StrategyRepo(pool, current_user.tenant_id)
    record = await repo.get_by_id(strategy_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    generated_logic: str = record["generated_logic"] or ""
    if len(generated_logic.strip()) < 30:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Strategy has no generated code yet. Build it first.",
        )

    import json as _json
    _rc = record["risk_config"]
    if isinstance(_rc, str):
        try:
            _rc = _json.loads(_rc)
        except Exception:
            _rc = {}
    risk_config = _rc if isinstance(_rc, dict) else {}

    # Fetch historical bars
    from app.services.market_data import get_bars
    bars = await get_bars(
        symbol=request.symbol.upper(),
        exchange=request.exchange.upper(),
        timeframe=request.timeframe,
        limit=request.limit,
        pool=pool,
    )
    if not bars or len(bars) < 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Insufficient data for {request.symbol} ({len(bars) if bars else 0} bars). Need ≥ 20.",
        )

    # Run backtest in thread pool (CPU-bound pandas/numpy)
    import asyncio
    from app.services.backtest import run_backtest, BacktestResult
    from app.services.strategy_sandbox import SandboxError

    try:
        result: BacktestResult = await asyncio.to_thread(
            run_backtest,
            str(strategy_id),
            generated_logic,
            bars,
            request.timeframe,
            risk_config,
            request.initial_equity,
        )
    except SandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Strategy code failed sandbox validation: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return BacktestResponse(
        strategy_id=str(strategy_id),
        symbol=result.symbol,
        timeframe=result.timeframe,
        bars_processed=result.bars_processed,
        trades=[
            BacktestTradeRecord(
                bar_index=t.bar_index,
                timestamp=t.timestamp,
                symbol=t.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
            )
            for t in result.trades
        ],
        equity_curve=result.equity_curve,
        metrics=BacktestMetricsModel(
            total_return_pct=result.metrics.total_return_pct,
            sharpe_ratio=result.metrics.sharpe_ratio,
            max_drawdown_pct=result.metrics.max_drawdown_pct,
            win_rate_pct=result.metrics.win_rate_pct,
            total_trades=result.metrics.total_trades,
            profitable_trades=result.metrics.profitable_trades,
            initial_equity=result.metrics.initial_equity,
            final_equity=result.metrics.final_equity,
        ),
        started_at=result.started_at,
        completed_at=result.completed_at,
    )
