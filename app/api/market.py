from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.rate_limit import limiter
from app.services import indicators as ind_svc
from app.services import market_data as md_svc
from app.services import symbol_search

router = APIRouter(prefix="/v1/market", tags=["market"])

_VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d", "1w"}
_VALID_EXCHANGES   = {"NASDAQ", "NYSE", "NSE", "BSE", "CRYPTO"}
_DEFAULT_INDICATORS = "rsi(14),macd(12,26,9),bb(20,2),ema(20),ema(50),ema(200),vwap"


def _parse_dt(s: str | None, param: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date for '{param}': {s!r}")


def _validate_timeframe(tf: str) -> None:
    if tf not in _VALID_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timeframe '{tf}'. Valid: {sorted(_VALID_TIMEFRAMES)}",
        )


def _validate_exchange(ex: str) -> None:
    if ex.upper() not in _VALID_EXCHANGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid exchange '{ex}'. Valid: {sorted(_VALID_EXCHANGES)}",
        )


@router.get("/bars/{symbol}")
@limiter.limit("60/minute")
async def get_bars(
    request: Request,
    symbol: str,
    timeframe: str = Query("1d"),
    exchange: str = Query("NASDAQ"),
    limit: int = Query(500, ge=1, le=1000),
    start: str | None = Query(None, description="ISO 8601 start date, e.g. 2024-01-01"),
    end: str | None = Query(None, description="ISO 8601 end date, e.g. 2024-06-01"),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[dict]:
    _validate_timeframe(timeframe)
    _validate_exchange(exchange)
    start_dt = _parse_dt(start, "start")
    end_dt   = _parse_dt(end,   "end")

    bars = await md_svc.get_bars(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        timeframe=timeframe,
        limit=limit,
        start=start_dt,
        end=end_dt,
        pool=pool,
    )
    return [b.to_dict() for b in bars]


@router.get("/indicators/{symbol}")
@limiter.limit("60/minute")
async def get_indicators(
    request: Request,
    symbol: str,
    timeframe: str = Query("1d"),
    exchange: str = Query("NASDAQ"),
    indicators: str = Query(_DEFAULT_INDICATORS),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    _validate_timeframe(timeframe)
    _validate_exchange(exchange)

    # Need enough bars for the longest indicator (ema_200 needs 200+ bars)
    bars = await md_svc.get_bars(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        timeframe=timeframe,
        limit=500,
        pool=pool,
    )
    if not bars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No market data found for {symbol} ({exchange})",
        )

    values = ind_svc.compute_indicators(bars, indicators)
    return {
        "symbol":     symbol.upper(),
        "exchange":   exchange.upper(),
        "timeframe":  timeframe,
        "timestamp":  bars[-1].timestamp.isoformat(),
        "close":      float(bars[-1].close),
        "indicators": values,
    }


@router.get("/search")
@limiter.limit("60/minute")
async def search_symbols(
    request: Request,
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(10, ge=1, le=30),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return symbol_search.search(q, limit=limit)
