"""
Parameterized technical indicator computation using pandas-ta.
ARCHITECTURE hard rule: pandas-ta only — no custom implementations, no TA-Lib.
Spec format: "rsi(14),macd(12,26,9),bb(20,2),ema(20),ema(50),ema(200),vwap,atr(14)"
Returns a flat dict of {key: float|None} for the most recent bar.
Keys follow pandas-ta uppercase convention: RSI_14, MACD_12_26_9, EMA_20, etc.
"""
import asyncio
import logging
import re

import pandas as pd
import pandas_ta as ta

from app.domain.market_data import Bar

logger = logging.getLogger(__name__)


def parse_specs(raw: str) -> list[tuple[str, list[float]]]:
    """Split "rsi(14),macd(12,26,9)" into [('rsi',[14.0]), ('macd',[12.0,26.0,9.0])].

    Uses findall so commas inside parentheses are not treated as spec separators.
    """
    result = []
    for part in re.findall(r'\w+(?:\([^)]*\))?', raw.lower()):
        m = re.match(r'^(\w+)(?:\(([^)]*)\))?$', part)
        if not m:
            logger.debug("Ignoring invalid indicator spec: %r", part)
            continue
        name = m.group(1)
        raw_args = m.group(2) or ""
        args = [float(a) for a in raw_args.split(",") if a.strip()]
        result.append((name, args))
    return result


def _to_df(bars: list[Bar]) -> pd.DataFrame:
    df = pd.DataFrame({
        "open":   [float(b.open)   for b in bars],
        "high":   [float(b.high)   for b in bars],
        "low":    [float(b.low)    for b in bars],
        "close":  [float(b.close)  for b in bars],
        "volume": [float(b.volume) for b in bars],
    })
    df.index = pd.DatetimeIndex([b.timestamp for b in bars])
    return df


def _last(series) -> float | None:
    if series is None:
        return None
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    if series is None or (hasattr(series, "empty") and series.empty):
        return None
    v = series.iloc[-1]
    return float(v) if pd.notna(v) else None


def _compute(df: pd.DataFrame, name: str, args: list[float], out: dict) -> None:
    if name == "rsi":
        n = int(args[0]) if args else 14
        result = ta.rsi(df["close"], length=n)
        if result is not None:
            out[f"RSI_{n}"] = _last(result)

    elif name == "macd":
        fast   = int(args[0]) if len(args) > 0 else 12
        slow   = int(args[1]) if len(args) > 1 else 26
        signal = int(args[2]) if len(args) > 2 else 9
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        if result is not None and not result.empty:
            for col in result.columns:
                out[col] = _last(result[col])

    elif name in ("bb", "bbands"):
        length = int(args[0]) if len(args) > 0 else 20
        std    = float(args[1]) if len(args) > 1 else 2.0
        result = ta.bbands(df["close"], length=length, std=std)
        if result is not None and not result.empty:
            for col in result.columns:
                out[col] = _last(result[col])

    elif name == "ema":
        n = int(args[0]) if args else 20
        result = ta.ema(df["close"], length=n)
        if result is not None:
            out[f"EMA_{n}"] = _last(result)

    elif name == "sma":
        n = int(args[0]) if args else 20
        result = ta.sma(df["close"], length=n)
        if result is not None:
            out[f"SMA_{n}"] = _last(result)

    elif name == "vwap":
        result = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        if result is not None:
            out["VWAP_D"] = _last(result)

    elif name == "atr":
        n = int(args[0]) if args else 14
        result = ta.atr(df["high"], df["low"], df["close"], length=n)
        if result is not None:
            out[f"ATRr_{n}"] = _last(result)

    elif name == "stoch":
        k = int(args[0]) if len(args) > 0 else 14
        d = int(args[1]) if len(args) > 1 else 3
        result = ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)
        if result is not None and not result.empty:
            for col in result.columns:
                out[col] = _last(result[col])

    elif name == "roc":
        n = int(args[0]) if args else 12
        result = ta.roc(df["close"], length=n)
        if result is not None:
            out[f"ROC_{n}"] = _last(result)


def _compute_indicators_sync(bars: list[Bar], specs: list[str] | str) -> dict[str, float | None]:
    if not bars:
        return {}
    if isinstance(specs, str):
        parsed = parse_specs(specs)
    else:
        parsed = []
        for s in specs:
            parsed.extend(parse_specs(s))

    df = _to_df(bars)
    out: dict[str, float | None] = {}

    for name, args in parsed:
        try:
            _compute(df, name, args, out)
        except Exception as exc:
            logger.debug("Indicator computation failed for %r(%s): %s", name, args, exc)

    return out


async def compute_indicators(bars: list[Bar], specs: list[str] | str) -> dict[str, float | None]:
    """Async wrapper — runs sync CPU-bound pandas-ta logic in a thread pool."""
    if not bars:
        return {}
    return await asyncio.to_thread(_compute_indicators_sync, bars, specs)
