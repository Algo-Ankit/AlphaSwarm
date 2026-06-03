"""
Market hours and timezone awareness.
Called by the Risk system as the first check before any order.
NSEpy is BANNED. This module handles all exchange scheduling.
"""
from datetime import datetime, time
from typing import Literal
import pytz


SessionStatus = Literal["pre_market", "open", "after_hours", "closed"]

_SCHEDULES: dict[str, dict] = {
    "NASDAQ": {
        "tz": "America/New_York",
        "open": time(9, 30),
        "close": time(16, 0),
        "pre_market_open": time(4, 0),
        "after_hours_close": time(20, 0),
        "weekdays": {0, 1, 2, 3, 4},  # Mon–Fri
    },
    "NYSE": {
        "tz": "America/New_York",
        "open": time(9, 30),
        "close": time(16, 0),
        "pre_market_open": time(4, 0),
        "after_hours_close": time(20, 0),
        "weekdays": {0, 1, 2, 3, 4},
    },
    "NSE": {
        "tz": "Asia/Kolkata",
        "open": time(9, 15),
        "close": time(15, 30),
        "pre_market_open": time(9, 0),
        "after_hours_close": time(15, 30),  # NSE has no official after-hours
        "weekdays": {0, 1, 2, 3, 4},
    },
    "BSE": {
        "tz": "Asia/Kolkata",
        "open": time(9, 15),
        "close": time(15, 30),
        "pre_market_open": time(9, 0),
        "after_hours_close": time(15, 30),
        "weekdays": {0, 1, 2, 3, 4},
    },
    "CRYPTO": {
        "tz": "UTC",
        "open": time(0, 0),
        "close": time(23, 59),
        "pre_market_open": time(0, 0),
        "after_hours_close": time(23, 59),
        "weekdays": {0, 1, 2, 3, 4, 5, 6},  # 24/7
    },
}


def get_session_status(exchange: str, now_utc: datetime | None = None) -> SessionStatus:
    """Return current session status for the given exchange."""
    schedule = _SCHEDULES.get(exchange.upper())
    if not schedule:
        return "closed"

    tz = pytz.timezone(schedule["tz"])
    now_local = (now_utc or datetime.utcnow().replace(tzinfo=pytz.utc)).astimezone(tz)

    if now_local.weekday() not in schedule["weekdays"]:
        return "closed"

    t = now_local.time()
    if schedule["open"] <= t < schedule["close"]:
        return "open"
    if schedule["pre_market_open"] <= t < schedule["open"]:
        return "pre_market"
    if schedule["close"] <= t <= schedule["after_hours_close"]:
        return "after_hours"
    return "closed"


def is_market_open(exchange: str, now_utc: datetime | None = None) -> bool:
    """True only during regular trading hours (not pre-market or after-hours)."""
    return get_session_status(exchange, now_utc) == "open"


def exchange_timezone(exchange: str) -> str:
    return _SCHEDULES.get(exchange.upper(), {}).get("tz", "UTC")
