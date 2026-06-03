"""
Market data service — canonical entry point for all OHLCV data.
Alpaca Data API for US stocks/crypto (with yfinance fallback).
yfinance for Indian (NSE/BSE) and global EOD data.
All output is normalized to app.domain.market_data.Bar. Nothing raw leaks out.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import asyncpg

from app.core.config import get_settings
from app.db.repositories.market_data import MarketDataRepo
from app.domain.market_data import Bar, to_yfinance_symbol

_settings = get_settings()

# How old the most-recent cached bar can be before we re-fetch from source
_STALE_AFTER: dict[str, timedelta] = {
    "1m":  timedelta(minutes=2),
    "5m":  timedelta(minutes=6),
    "15m": timedelta(minutes=20),
    "1h":  timedelta(hours=2),
    "4h":  timedelta(hours=5),
    "1d":  timedelta(hours=25),
    "1w":  timedelta(days=8),
}

# yfinance (interval, period_fallback) — period is used when start is not supplied
_YF_PARAMS: dict[str, tuple[str, str]] = {
    "1m":  ("1m",  "5d"),
    "5m":  ("5m",  "60d"),
    "15m": ("15m", "60d"),
    "1h":  ("1h",  "730d"),
    "4h":  ("1h",  "730d"),   # yfinance has no native 4h; 1h bars used
    "1d":  ("1d",  "max"),
    "1w":  ("1wk", "max"),
}


def _alpaca_timeframe(tf: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    return {
        "1m":  TimeFrame.Minute,
        "5m":  TimeFrame(5,  TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h":  TimeFrame.Hour,
        "4h":  TimeFrame(4,  TimeFrameUnit.Hour),
        "1d":  TimeFrame.Day,
        "1w":  TimeFrame.Week,
    }[tf]


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _record_to_bar(row: asyncpg.Record, symbol: str, exchange: str, timeframe: str) -> Bar:
    return Bar(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        timeframe=timeframe,
        timestamp=_utc(row["bar_time"]),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=int(row["volume"] or 0),
    )


def _is_us(exchange: str) -> bool:
    return exchange.upper() in ("NASDAQ", "NYSE")


def _is_crypto(exchange: str) -> bool:
    return exchange.upper() == "CRYPTO"


async def _fetch_alpaca(
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int,
    start: datetime | None,
    end: datetime | None,
) -> list[Bar]:
    api_key = _settings.alpaca_api_key
    secret_key = _settings.alpaca_secret_key
    if not api_key or not secret_key:
        return []

    def _sync() -> list[Bar]:
        tf = _alpaca_timeframe(timeframe)
        if _is_crypto(exchange):
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoBarsRequest
            client = CryptoHistoricalDataClient(api_key, secret_key)
            req = CryptoBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
            )
            resp = client.get_crypto_bars(req)
        else:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.enums import Adjustment
            client = StockHistoricalDataClient(api_key, secret_key)
            req = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
                adjustment=Adjustment.ALL,
            )
            resp = client.get_stock_bars(req)

        raw = resp.get(symbol.upper(), [])
        return [
            Bar(
                symbol=symbol.upper(),
                exchange=exchange.upper(),
                timeframe=timeframe,
                timestamp=_utc(b.timestamp),
                open=Decimal(str(b.open)),
                high=Decimal(str(b.high)),
                low=Decimal(str(b.low)),
                close=Decimal(str(b.close)),
                volume=int(b.volume or 0),
            )
            for b in raw
        ]

    try:
        return await asyncio.to_thread(_sync)
    except Exception:
        return []


async def _fetch_yfinance(
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int,
    start: datetime | None,
    end: datetime | None,
) -> list[Bar]:
    yf_symbol = to_yfinance_symbol(symbol, exchange)
    yf_interval, yf_period = _YF_PARAMS.get(timeframe, ("1d", "max"))

    def _sync() -> list[Bar]:
        import pandas as pd
        import yfinance as yf

        ticker = yf.Ticker(yf_symbol)
        if start:
            df = ticker.history(start=start, end=end, interval=yf_interval)
        else:
            df = ticker.history(period=yf_period, interval=yf_interval)

        if df is None or df.empty:
            return []

        df = df.rename(columns=str.lower)
        df.index = pd.to_datetime(df.index, utc=True)

        bars: list[Bar] = []
        for ts, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol.upper(),
                exchange=exchange.upper(),
                timeframe=timeframe,
                timestamp=ts.to_pydatetime(),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=int(row.get("volume", 0) or 0),
            ))
        return bars[-limit:]

    try:
        return await asyncio.to_thread(_sync)
    except Exception:
        return []


async def get_bars(
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int = 500,
    start: datetime | None = None,
    end: datetime | None = None,
    pool: asyncpg.Pool | None = None,
) -> list[Bar]:
    """
    Returns bars sorted oldest-first.
    Checks DB cache first; fetches from Alpaca or yfinance on miss/stale.
    """
    repo = MarketDataRepo(pool) if pool else None

    # Cache check
    if repo:
        stale_after = _STALE_AFTER.get(timeframe, timedelta(hours=25))
        latest = await repo.latest_bar_time(symbol, exchange, timeframe)
        if latest and (datetime.now(timezone.utc) - _utc(latest)) < stale_after:
            rows = await repo.get_bars(symbol, exchange, timeframe, start=start, end=end, limit=limit)
            if rows:
                return [_record_to_bar(r, symbol, exchange, timeframe) for r in rows]

    # Fetch from source
    if _is_us(exchange) or _is_crypto(exchange):
        bars = await _fetch_alpaca(symbol, exchange, timeframe, limit, start, end)
        if not bars:
            bars = await _fetch_yfinance(symbol, exchange, timeframe, limit, start, end)
    else:
        bars = await _fetch_yfinance(symbol, exchange, timeframe, limit, start, end)

    if repo and bars:
        await repo.bulk_upsert(bars)

    # Apply date filters and limit on live data
    if start:
        start_utc = _utc(start)
        bars = [b for b in bars if b.timestamp >= start_utc]
    if end:
        end_utc = _utc(end)
        bars = [b for b in bars if b.timestamp <= end_utc]

    return bars[-limit:]
