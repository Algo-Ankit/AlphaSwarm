"""
Parameterized technical indicator computation via pandas-ta.
Spec format: "rsi(14),macd(12,26,9),bb(20,2),ema(20),ema(50),ema(200),vwap,atr(14)"
Returns a flat dict of {key: float|None} for the most recent bar.
"""
import logging
import re

import pandas as pd
import pandas_ta as ta

from app.domain.market_data import Bar

logger = logging.getLogger(__name__)


def parse_specs(raw: str) -> list[tuple[str, list[float]]]:
    """Split "rsi(14),macd(12,26,9)" into [('rsi',[14.0]), ('macd',[12.0,26.0,9.0])].

    Uses findall so commas inside parentheses (e.g. macd args) are not treated as
    spec separators — naive split(",") breaks multi-argument indicators.
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
    return pd.DataFrame({
        "open":   [float(b.open)   for b in bars],
        "high":   [float(b.high)   for b in bars],
        "low":    [float(b.low)    for b in bars],
        "close":  [float(b.close)  for b in bars],
        "volume": [float(b.volume) for b in bars],
    })


def _last(series) -> float | None:
    """Return the last non-null value from a Series or DataFrame column."""
    if series is None:
        return None
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    if series.empty:
        return None
    v = series.iloc[-1]
    return float(v) if pd.notna(v) else None


import asyncio

async def compute_indicators(bars: list[Bar], specs: list[str] | str) -> dict[str, float | None]:
    """
    Compute all requested indicators on the provided bars.
    `specs` may be a list of strings or a single comma-separated string.
    Returns values for the most recent (last) bar only.
    Runs the synchronous CPU-bound pandas logic in a thread pool.
    """
    if not bars:
        return {}
        
    return await asyncio.to_thread(_compute_indicators_sync, bars, specs)

def _compute_indicators_sync(bars: list[Bar], specs: list[str] | str) -> dict[str, float | None]:
    """Synchronous core logic executed in a worker thread."""
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


def _compute(df: pd.DataFrame, name: str, args: list[float], out: dict) -> None:
    if name == "rsi":
        n = int(args[0]) if args else 14
        out[f"rsi_{n}"] = _last(ta.rsi(df["close"], length=n))

    elif name == "macd":
        fast   = int(args[0]) if len(args) > 0 else 12
        slow   = int(args[1]) if len(args) > 1 else 26
        signal = int(args[2]) if len(args) > 2 else 9
        res = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        if res is not None and not res.empty:
            cols = res.columns.tolist()
            out[f"macd_{fast}_{slow}_{signal}"]  = _last(res[cols[0]])   # MACD line
            out[f"macdh_{fast}_{slow}_{signal}"] = _last(res[cols[1]])   # Histogram
            out[f"macds_{fast}_{slow}_{signal}"] = _last(res[cols[2]])   # Signal

    elif name in ("bb", "bbands"):
        length = int(args[0]) if len(args) > 0 else 20
        std    = float(args[1]) if len(args) > 1 else 2.0
        res = ta.bbands(df["close"], length=length, std=std)
        if res is not None and not res.empty:
            cols = res.columns.tolist()
            out[f"bbl_{length}_{std}"] = _last(res[cols[0]])   # Lower
            out[f"bbm_{length}_{std}"] = _last(res[cols[1]])   # Middle
            out[f"bbu_{length}_{std}"] = _last(res[cols[2]])   # Upper
            out[f"bbw_{length}_{std}"] = _last(res[cols[3]])   # Bandwidth
            out[f"bbp_{length}_{std}"] = _last(res[cols[4]])   # Percent B

    elif name == "ema":
        n = int(args[0]) if args else 20
        out[f"ema_{n}"] = _last(ta.ema(df["close"], length=n))

    elif name == "sma":
        n = int(args[0]) if args else 20
        out[f"sma_{n}"] = _last(ta.sma(df["close"], length=n))

    elif name == "vwap":
        res = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        out["vwap"] = _last(res)

    elif name == "atr":
        n = int(args[0]) if args else 14
        out[f"atr_{n}"] = _last(ta.atr(df["high"], df["low"], df["close"], length=n))

    elif name == "stoch":
        k = int(args[0]) if len(args) > 0 else 14
        d = int(args[1]) if len(args) > 1 else 3
        res = ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)
        if res is not None and not res.empty:
            cols = res.columns.tolist()
            out[f"stochk_{k}_{d}"] = _last(res[cols[0]])
            out[f"stochd_{k}_{d}"] = _last(res[cols[1]])

    elif name == "roc":
        n = int(args[0]) if args else 12
        out[f"roc_{n}"] = _last(ta.roc(df["close"], length=n))
