"""
Portfolio ingestion — parse a (simulated) NSDL/CDSL Consolidated Account
Statement into normalised `unified_holdings` rows.

For the MVP the endpoint accepts an already-extracted JSON payload rather than a
raw PDF/eCAS file; this service validates, normalises and prices each line so the
rest of the platform sees one canonical holding shape regardless of the source
broker. The platform never custodies these assets — rows are a read-only mirror
of what the user holds at their own brokers/depositories.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

_VALID_ASSET_CLASSES = {"equity", "mutual_fund", "etf", "bond", "other"}


def _to_decimal(value, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for '{field}': {value!r}") from exc


def normalize_holding(raw: dict) -> dict:
    """
    Normalise a single CAS line into the `unified_holdings` row shape.
    Raises ValueError on malformed input. current_value is computed from the
    current price when available, otherwise it falls back to cost basis so the
    consolidated total is never silently zero.
    """
    symbol = (raw.get("symbol") or "").strip().upper()
    name = (raw.get("name") or "").strip()
    if not symbol:
        raise ValueError("Holding is missing a 'symbol'")
    if not name:
        name = symbol

    asset_class = (raw.get("asset_class") or "equity").strip().lower()
    if asset_class not in _VALID_ASSET_CLASSES:
        asset_class = "other"

    broker = (raw.get("broker") or "Unknown").strip()
    isin = raw.get("isin") or None
    if isin:
        isin = isin.strip().upper() or None

    quantity = _to_decimal(raw.get("quantity", 0), "quantity")
    if quantity <= 0:
        raise ValueError(f"Holding '{symbol}' has non-positive quantity {quantity}")
    avg_cost = _to_decimal(raw.get("avg_cost", 0), "avg_cost")

    current_price_raw = raw.get("current_price")
    current_price = (
        _to_decimal(current_price_raw, "current_price") if current_price_raw is not None else None
    )

    price_for_value = current_price if current_price is not None else avg_cost
    current_value = (quantity * price_for_value).quantize(Decimal("0.00000001"))

    return {
        "isin": isin,
        "symbol": symbol,
        "name": name,
        "asset_class": asset_class,
        "broker": broker,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "current_price": current_price,
        "current_value": current_value,
    }


def parse_cas(holdings_raw: list[dict]) -> list[dict]:
    """
    Validate and normalise a full CAS holdings payload.
    Raises ValueError (with the offending index) if any line is malformed so the
    caller can return a 422 rather than persisting a partial statement.
    """
    if not holdings_raw:
        return []
    parsed: list[dict] = []
    for i, raw in enumerate(holdings_raw):
        try:
            parsed.append(normalize_holding(raw))
        except ValueError as exc:
            raise ValueError(f"Holding #{i + 1}: {exc}") from exc
    return parsed


def summarize(parsed: list[dict], statement_date: date | None) -> dict:
    """Aggregate totals + per-broker / per-asset-class breakdowns for the API."""
    total_value = sum((h["current_value"] for h in parsed), Decimal(0))
    total_cost = sum((h["quantity"] * h["avg_cost"] for h in parsed), Decimal(0))
    unrealized = total_value - total_cost

    by_broker: dict[str, Decimal] = {}
    by_class: dict[str, Decimal] = {}
    for h in parsed:
        by_broker[h["broker"]] = by_broker.get(h["broker"], Decimal(0)) + h["current_value"]
        by_class[h["asset_class"]] = by_class.get(h["asset_class"], Decimal(0)) + h["current_value"]

    return {
        "statement_date": statement_date.isoformat() if statement_date else None,
        "holdings_count": len(parsed),
        "total_value": float(total_value),
        "total_cost": float(total_cost),
        "unrealized_pnl": float(unrealized),
        "unrealized_pnl_pct": float(unrealized / total_cost * 100) if total_cost > 0 else 0.0,
        "by_broker": {k: float(v) for k, v in by_broker.items()},
        "by_asset_class": {k: float(v) for k, v in by_class.items()},
    }
