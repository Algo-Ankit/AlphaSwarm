"""
Single source of truth for which broker executes a given exchange's orders and
which currency that exchange settles in.

Keeps broker selection out of the worker (was hardcoded to "alpaca") and currency
out of hardcoded "$" risk messages. A strategy on NSE must route to an Indian
broker and quote limits in ₹, not be silently sent to a US broker in $.
"""
from __future__ import annotations

from decimal import Decimal

# exchange (UPPER) → broker key as stored in the `brokers` table `broker` column
_EXCHANGE_BROKER: dict[str, str] = {
    "NASDAQ": "alpaca",
    "NYSE": "alpaca",
    "CRYPTO": "alpaca",
    "NSE": "upstox",
    "BSE": "upstox",
}

# exchange (UPPER) → ISO-4217 currency the market settles in
_EXCHANGE_CURRENCY: dict[str, str] = {
    "NASDAQ": "USD",
    "NYSE": "USD",
    "CRYPTO": "USD",
    "NSE": "INR",
    "BSE": "INR",
}

_CURRENCY_SYMBOL: dict[str, str] = {
    "USD": "$",
    "INR": "₹",
    "EUR": "€",
    "GBP": "£",
}

DEFAULT_BROKER = "alpaca"
DEFAULT_CURRENCY = "USD"

# Exchanges that legally forbid fractional EQUITY shares. Indian cash-market
# equity (NSE/BSE) settles only in whole shares — a 1.66-share order is rejected
# by the exchange. US equity (Alpaca) supports fractional, and crypto is
# inherently fractional, so those are intentionally absent here.
NON_FRACTIONAL_EXCHANGES: frozenset[str] = frozenset({"NSE", "BSE"})

# Currency the platform-level caps (settings.default_max_order_notional, etc.)
# are denominated in. Single source of truth — risk.py converts order notionals
# into this currency (or the cap into the order's currency) before comparing.
PLATFORM_CAP_CURRENCY = "USD"

# Static reference FX rates: units of the given currency per 1 USD.
# Used ONLY to compare order notionals against the USD-denominated platform cap.
# This is a risk guardrail, NOT accounting — the platform never handles funds,
# so approximate static rates are acceptable and intentionally conservative.
_UNITS_PER_USD: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "INR": Decimal("83"),
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.79"),
}


def broker_for_exchange(exchange: str) -> str:
    """Broker key that should execute orders for this exchange."""
    return _EXCHANGE_BROKER.get((exchange or "").upper(), DEFAULT_BROKER)


def currency_for_exchange(exchange: str) -> str:
    """Settlement currency (ISO code) for this exchange."""
    return _EXCHANGE_CURRENCY.get((exchange or "").upper(), DEFAULT_CURRENCY)


def allows_fractional_shares(exchange: str) -> bool:
    """False for exchanges that forbid fractional equity (NSE/BSE); True otherwise."""
    return (exchange or "").upper() not in NON_FRACTIONAL_EXCHANGES


def currency_symbol(currency: str) -> str:
    """Display symbol for a currency code; falls back to 'CODE ' (e.g. 'AUD ')."""
    code = (currency or DEFAULT_CURRENCY).upper()
    return _CURRENCY_SYMBOL.get(code, f"{code} ")


def convert_amount(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    """Convert an amount between currencies using static reference rates.

    Returns a Decimal in `to_currency`. Unknown currencies are treated as a
    1:1 rate (no conversion) so a missing rate fails *open* on display but the
    caller can still detect it via `has_fx_rate`. Used by risk.py so the
    USD-denominated platform cap can be compared against non-USD order notionals.
    """
    src = (from_currency or DEFAULT_CURRENCY).upper()
    dst = (to_currency or DEFAULT_CURRENCY).upper()
    if src == dst:
        return Decimal(str(amount))
    src_rate = _UNITS_PER_USD.get(src, Decimal("1"))
    dst_rate = _UNITS_PER_USD.get(dst, Decimal("1"))
    amount_usd = Decimal(str(amount)) / src_rate
    return amount_usd * dst_rate


def has_fx_rate(currency: str) -> bool:
    """True if we hold a reference FX rate for this currency."""
    return (currency or DEFAULT_CURRENCY).upper() in _UNITS_PER_USD
