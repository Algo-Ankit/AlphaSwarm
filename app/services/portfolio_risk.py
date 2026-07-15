"""
Deterministic portfolio risk engine.

Scores a set of unified (multi-broker) holdings for concentration, drawdown and
diversification risk WITHOUT any LLM — so the risk view is instant, free, and
identical for every user regardless of whether they've added an AI key. The AI
advisor (services/ai_advisor.review_holdings) sits on top of this: it turns the
numbers computed here into plain-English "trim / sell / hold" guidance.

The platform never custodies these assets — holdings are a read-only mirror of
what the user holds at their own brokers, so "sell/trim" is advice, never an
action taken on their behalf.
"""

from __future__ import annotations

# Signals, most-to-least urgent. "Trim" = reduce an oversized winner; "Review"
# = a losing position worth a decision; "Hold" = no action indicated.
SIGNAL_TRIM = "Trim"
SIGNAL_REVIEW = "Review"
SIGNAL_HOLD = "Hold"

# Thresholds (fractions / percentages). Deliberately conservative and explicit.
_CONCENTRATION_WARN = 0.20   # one holding > 20% of net worth
_CONCENTRATION_HIGH = 0.35   # one holding > 35% is a real single-name risk
_DRAWDOWN_REVIEW = -20.0     # a position down > 20% deserves a review
_BROKER_CONCENTRATION = 0.70  # > 70% at one broker = single-broker concentration risk
_ASSET_CONCENTRATION = 0.80  # > 80% in one asset class = undiversified


def _holding_value(h: dict) -> float:
    """Current market value; falls back to cost basis if no price is available."""
    cv = h.get("current_value")
    if cv is not None:
        return float(cv)
    qty = float(h.get("quantity", 0) or 0)
    price = h.get("current_price")
    if price is None:
        price = h.get("avg_cost", 0)
    return qty * float(price or 0)


def _unrealized_pct(h: dict) -> float | None:
    """Unrealized P&L % vs cost basis, or None when cost is unknown/zero."""
    qty = float(h.get("quantity", 0) or 0)
    avg_cost = float(h.get("avg_cost", 0) or 0)
    cost = qty * avg_cost
    if cost <= 0:
        return None
    return (_holding_value(h) - cost) / cost * 100.0


def analyze_holdings(holdings: list[dict]) -> dict:
    """
    Return a per-holding + portfolio-level risk scorecard.

    Each holding gets a weight, unrealized-P&L %, a signal (Trim/Review/Hold) and
    human-readable reasons. Portfolio level reports a concentration index (HHI),
    the largest single position, broker/asset-class concentration, and a plain
    verdict. Pure function — deterministic and side-effect free.
    """
    total = sum(_holding_value(h) for h in holdings)
    if total <= 0 or not holdings:
        return {
            "total_value": round(total, 2),
            "holdings_count": len(holdings),
            "concentration_index": 0.0,
            "top_weight_pct": 0.0,
            "broker_concentration_pct": 0.0,
            "asset_class_concentration_pct": 0.0,
            "diversification": "unknown",
            "flagged_count": 0,
            "verdict": "No priced holdings to analyze yet.",
            "holdings": [],
        }

    by_broker: dict[str, float] = {}
    by_class: dict[str, float] = {}
    scored: list[dict] = []
    hhi = 0.0

    for h in holdings:
        value = _holding_value(h)
        weight = value / total  # 0..1
        hhi += weight * weight
        by_broker[h.get("broker", "Unknown")] = by_broker.get(h.get("broker", "Unknown"), 0.0) + value
        cls = h.get("asset_class", "other")
        by_class[cls] = by_class.get(cls, 0.0) + value

        pnl_pct = _unrealized_pct(h)
        reasons: list[str] = []
        signal = SIGNAL_HOLD

        if weight >= _CONCENTRATION_HIGH:
            signal = SIGNAL_TRIM
            reasons.append(
                f"{weight * 100:.0f}% of your net worth sits in this one name — a large "
                "single-stock risk. Consider trimming to cap the downside."
            )
        elif weight >= _CONCENTRATION_WARN:
            signal = SIGNAL_TRIM
            reasons.append(
                f"{weight * 100:.0f}% concentration in a single holding is above a prudent "
                "20% — trimming would reduce idiosyncratic risk."
            )

        if pnl_pct is not None and pnl_pct <= _DRAWDOWN_REVIEW:
            # A deep loser is a decision point, not an automatic sell.
            if signal == SIGNAL_HOLD:
                signal = SIGNAL_REVIEW
            reasons.append(
                f"Down {abs(pnl_pct):.0f}% from your cost — review the thesis: average down, "
                "hold, or cut the loss."
            )

        if signal == SIGNAL_HOLD:
            reasons.append("Sized and performing within normal bounds — no action indicated.")

        scored.append(
            {
                "symbol": h.get("symbol", ""),
                "name": h.get("name", ""),
                "broker": h.get("broker", "Unknown"),
                "value": round(value, 2),
                "weight_pct": round(weight * 100, 1),
                "unrealized_pnl_pct": round(pnl_pct, 1) if pnl_pct is not None else None,
                "signal": signal,
                "reasons": reasons,
            }
        )

    # Portfolio-level rollups.
    top = max(scored, key=lambda s: s["weight_pct"])
    top_broker_pct = max(by_broker.values()) / total * 100
    top_class_pct = max(by_class.values()) / total * 100
    flagged = sum(1 for s in scored if s["signal"] != SIGNAL_HOLD)

    # HHI: ~1/N (well diversified) → 1.0 (single position). Map to a verdict.
    if hhi >= 0.40:
        diversification = "concentrated"
    elif hhi >= 0.20:
        diversification = "moderate"
    else:
        diversification = "diversified"

    verdict_bits: list[str] = []
    if top["weight_pct"] >= _CONCENTRATION_WARN * 100:
        verdict_bits.append(
            f"{top['symbol']} is your biggest risk at {top['weight_pct']:.0f}% of net worth"
        )
    if top_broker_pct >= _BROKER_CONCENTRATION * 100:
        verdict_bits.append(
            f"{top_broker_pct:.0f}% of assets sit at a single broker — spread across more brokers"
        )
    if top_class_pct >= _ASSET_CONCENTRATION * 100:
        verdict_bits.append(
            f"{top_class_pct:.0f}% is in one asset class — diversification is thin"
        )
    if not verdict_bits:
        verdict_bits.append("Well spread across positions, brokers and asset classes.")

    return {
        "total_value": round(total, 2),
        "holdings_count": len(holdings),
        "concentration_index": round(hhi, 3),
        "top_weight_pct": top["weight_pct"],
        "broker_concentration_pct": round(top_broker_pct, 1),
        "asset_class_concentration_pct": round(top_class_pct, 1),
        "diversification": diversification,
        "flagged_count": flagged,
        "verdict": " · ".join(verdict_bits),
        "holdings": sorted(scored, key=lambda s: s["weight_pct"], reverse=True),
    }
