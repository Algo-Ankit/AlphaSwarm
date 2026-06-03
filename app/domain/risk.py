"""
Centralized risk verification. Called before EVERY broker API call.
This function is the safety wall. It must never be bypassed.
Adding a new check: add it here, not in strategy code.
"""
from app.core.config import Settings, get_settings
from app.domain.market_data import MarketState
from app.domain.market_hours import is_market_open
from app.domain.models import OrderIntent, RiskCheckResult, StrategyRiskConfig


def verify_order_intent(
    order: OrderIntent,
    strategy_risk: StrategyRiskConfig,
    market_state: MarketState | None = None,
    settings: Settings | None = None,
) -> RiskCheckResult:
    """
    Validates an order intent against all risk rules.
    Returns RiskCheckResult with approved=True only if ALL checks pass.
    Checks are ordered from fastest/cheapest to slowest.

    Args:
        order: The proposed order.
        strategy_risk: Per-strategy risk config.
        market_state: Current market state (hours, today's notional, open exposure).
                      If None, market hours check is skipped (use in backtesting only).
        settings: App settings. Defaults to singleton.
    """
    settings = settings or get_settings()
    symbol = order.symbol.upper()
    notional = order.estimated_notional

    # ── Check 1: Market is open (skip during backtesting when market_state is None) ──
    if market_state is not None:
        if not market_state.is_open:
            return RiskCheckResult(
                approved=False,
                reason=f"Market is {market_state.session_status} for {market_state.exchange}. No orders outside regular trading hours.",
                order_notional=notional,
            )

    # ── Check 2: Paper trading gate ──────────────────────────────────────────
    if strategy_risk.paper_trading_only and not order.is_paper:
        return RiskCheckResult(
            approved=False,
            reason="Strategy is configured for paper trading only. Enable live trading in strategy settings.",
            order_notional=notional,
        )

    # ── Check 3: Symbol allowed by strategy ──────────────────────────────────
    if strategy_risk.allowed_symbols:
        allowed = {s.upper() for s in strategy_risk.allowed_symbols}
        if symbol not in allowed:
            return RiskCheckResult(
                approved=False,
                reason=f"{symbol} is not in this strategy's allowed symbols list.",
                order_notional=notional,
            )

    # ── Check 4: Order notional ≤ strategy limit ─────────────────────────────
    if notional > strategy_risk.max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional ${notional:.2f} exceeds strategy limit ${strategy_risk.max_order_notional:.2f}.",
            order_notional=notional,
        )

    # ── Check 5: Today's executed notional ≤ daily limit ─────────────────────
    if market_state is not None:
        projected_daily = market_state.today_executed_notional + notional
        if projected_daily > strategy_risk.max_daily_notional:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Order would bring today's total to ${projected_daily:.2f}, "
                    f"exceeding the daily limit of ${strategy_risk.max_daily_notional:.2f}."
                ),
                order_notional=notional,
            )

    # ── Check 6: Platform-level order notional cap ────────────────────────────
    if notional > settings.default_max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional ${notional:.2f} exceeds platform-level cap ${settings.default_max_order_notional:.2f}.",
            order_notional=notional,
        )

    return RiskCheckResult(
        approved=True,
        reason="Order passed all risk checks.",
        order_notional=notional,
    )
