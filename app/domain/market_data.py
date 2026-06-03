"""
Canonical market data models. All sources (Alpaca, yfinance, Zerodha)
must be normalized to Bar before leaving the market_data service.
Nothing outside app/services/market_data.py should import raw provider objects.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Exchange(str, Enum):
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    NSE = "NSE"
    BSE = "BSE"
    CRYPTO = "CRYPTO"


class Timeframe(str, Enum):
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"


@dataclass(frozen=True)
class Bar:
    """
    Canonical OHLCV bar. Immutable. All timestamps are UTC.
    This is the only market data representation used outside the market_data service.
    """
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime      # UTC bar close time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
        }


@dataclass
class MarketState:
    """Snapshot of market conditions at the moment of an order decision."""
    exchange: str
    is_open: bool
    session_status: str        # pre_market | open | after_hours | closed
    today_executed_notional: float = 0.0
    total_open_position_value: float = 0.0


# yfinance symbol suffixes for Indian markets
EXCHANGE_YFINANCE_SUFFIX: dict[str, str] = {
    "NSE": ".NS",
    "BSE": ".BO",
}

def to_yfinance_symbol(symbol: str, exchange: str) -> str:
    """Convert 'RELIANCE' + 'NSE' → 'RELIANCE.NS'"""
    suffix = EXCHANGE_YFINANCE_SUFFIX.get(exchange, "")
    if suffix and not symbol.endswith(suffix):
        return f"{symbol}{suffix}"
    return symbol
