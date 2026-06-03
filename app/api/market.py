from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.rate_limit import limiter
from app.services import forecaster as fc_svc
from app.services import indicators as ind_svc
from app.services import market_data as md_svc
from app.services import news_intel as news_svc
from app.services import symbol_search
from app.services.news_intel import IntelligenceServiceError

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

    values = await ind_svc.compute_indicators(bars, indicators)
    return {
        "symbol":     symbol.upper(),
        "exchange":   exchange.upper(),
        "timeframe":  timeframe,
        "timestamp":  bars[-1].timestamp.isoformat(),
        "close":      float(bars[-1].close),
        "indicators": values,
    }


@router.get("/forecast/{symbol}")
@limiter.limit("60/minute")
async def get_forecast(
    request: Request,
    symbol: str,
    horizon: int = Query(5, ge=1, le=30, description="Forecast horizon in trading days"),
    exchange: str = Query("NASDAQ"),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    _validate_exchange(exchange)
    try:
        result = await fc_svc.get_forecast(
            symbol=symbol.upper(),
            exchange=exchange.upper(),
            horizon_days=horizon,
            pool=pool,
        )
        return result.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Forecast computation failed: {exc}",
        )


@router.get("/news/{symbol}")
@limiter.limit("60/minute")
async def get_news(
    request: Request,
    symbol: str,
    exchange: str = Query("NASDAQ"),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(20, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[dict]:
    _validate_exchange(exchange)
    try:
        items = await news_svc.get_news(
            symbol=symbol.upper(),
            exchange=exchange.upper(),
            days=days,
            limit=limit,
            pool=pool,
        )
        return [item.to_dict() for item in items]
    except IntelligenceServiceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.get("/search")
@limiter.limit("60/minute")
async def search_symbols(
    request: Request,
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(10, ge=1, le=30),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return symbol_search.search(q, limit=limit)
