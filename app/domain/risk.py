"""
Centralized risk verification. Called before EVERY broker API call.
This function is the safety wall. It must never be bypassed.
Adding a new check: add it here, not in strategy code.
"""
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.domain.broker_routing import (
    PLATFORM_CAP_CURRENCY,
    allows_fractional_shares,
    convert_amount,
    currency_symbol,
)
from app.domain.market_data import MarketState
from app.domain.market_hours import is_market_open
from app.domain.models import OrderIntent, OrderSide, RiskCheckResult, StrategyRiskConfig

# When no real-time tick is available, the daily-notional cap must not blindly
# trust yesterday's close (order.estimated_price). A stock that gaps up violently
# at the open can blow past the rupee cap while the stale-price math still reads
# "under limit". We size the cap on the close inflated by this safety margin so
# the guardrail fails CLOSED on an open gap. Only ever tightens the cap.
GAP_SAFETY_MARGIN = Decimal("0.03")  # 3%


def verify_order_intent(
    order: OrderIntent,
    strategy_risk: StrategyRiskConfig,
    market_state: MarketState | None = None,
    settings: Settings | None = None,
    current_position: float | None = None,
    current_position_value: float | None = None,
    open_positions_count: int = 0,
    reference_price: Decimal | None = None,
) -> RiskCheckResult:
    """
    Validates an order intent against all risk rules.
    Returns RiskCheckResult with approved=True only if ALL checks pass.

    Args:
        order: The proposed order.
        strategy_risk: Per-strategy risk config.
        market_state: Current market state. If None, market hours check is skipped (backtesting).
        settings: App settings. Defaults to singleton.
        current_position: Current held quantity for this symbol (positive=long, negative=short, None/0=flat).
                          Used to determine whether an order is risk-reducing or risk-adding.
        reference_price: Real-time tick/last-trade price, if available. Used by the daily
                         notional cap (Check 5) to defend against open gaps. When omitted,
                         the cap falls back to estimated_price inflated by GAP_SAFETY_MARGIN.
    """
    settings = settings or get_settings()
    symbol = order.symbol.upper()
    notional = order.estimated_notional
    cur = currency_symbol(strategy_risk.currency)  # $, ₹, … for user-facing amounts

    # ── Check 1: Market is open ───────────────────────────────────────────────
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
    allowed = {s.upper() for s in strategy_risk.allowed_symbols}
    if symbol not in allowed:
        return RiskCheckResult(
            approved=False,
            reason=f"{symbol} is not in this strategy's allowed symbols list.",
            order_notional=notional,
        )

    # ── Check 3a: Whole-share enforcement (no fractional equity) ─────────────
    # Indian cash-market equity (NSE/BSE) rejects fractional quantities outright.
    # Catch it here rather than letting the broker reject it (or, worse, letting a
    # SIP attempt to buy 1.66 shares). US equity / crypto allow fractional, so this
    # is a no-op there. The SIP allocator floors qty upstream; this is the wall.
    if not allows_fractional_shares(order.exchange):
        if order.quantity != order.quantity.to_integral_value():
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"{symbol} on {order.exchange} allows whole shares only; "
                    f"order quantity {order.quantity} is fractional. Floor the allocation to an integer."
                ),
                order_notional=notional,
            )

    # ── Determine safe cap price for ALL notional checks ─────────────────────
    if reference_price is not None and reference_price > 0 and market_state is not None and market_state.is_open:
        cap_price = reference_price
    else:
        cap_price = order.estimated_price * (Decimal("1") + GAP_SAFETY_MARGIN)

    safe_notional = order.quantity * cap_price

    # ── Check 4: Order notional ≤ strategy limit ─────────────────────────────
    if safe_notional > strategy_risk.max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional {cur}{safe_notional:.2f} exceeds strategy limit {cur}{strategy_risk.max_order_notional:.2f}.",
            order_notional=safe_notional,
        )

    # ── Check 4a: Per-symbol position notional cap ────────────────────────────
    pos = current_position or 0.0
    
    side_sign = Decimal("1") if order.side == OrderSide.buy else Decimal("-1")
    delta = order.quantity * side_sign
    projected_position_qty = Decimal(str(pos)) + delta
    
    is_increasing_exposure = False
    if pos >= 0 and order.side == OrderSide.buy:
        is_increasing_exposure = True
    elif pos <= 0 and order.side == OrderSide.sell:
        is_increasing_exposure = True
    elif abs(projected_position_qty) > abs(Decimal(str(pos))):
        is_increasing_exposure = True  # Stop-and-reverse overshoot
        
    if current_position_value is not None and is_increasing_exposure:
        # If it was a stop-and-reverse, the new risk exposure is the absolute size of the new position.
        # If just adding to a position, it's the current value + new order value.
        if (pos > 0 and order.side == OrderSide.sell) or (pos < 0 and order.side == OrderSide.buy):
            projected_position = abs(projected_position_qty) * cap_price
        else:
            projected_position = Decimal(str(current_position_value)) + safe_notional
        if projected_position > strategy_risk.max_position_notional:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Order would bring {symbol} exposure to {cur}{projected_position:.2f}, "
                    f"exceeding the per-symbol position limit of {cur}{strategy_risk.max_position_notional:.2f}."
                ),
                order_notional=safe_notional,
            )

    # ── Check 4b: Max concurrent open positions ───────────────────────────────
    if pos == 0.0 and is_increasing_exposure:
        if open_positions_count >= strategy_risk.max_open_positions:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Strategy has {open_positions_count} open positions at the limit of "
                    f"{strategy_risk.max_open_positions}. Close an existing position before opening {symbol}."
                ),
                order_notional=safe_notional,
            )

    # ── Check 5: Today's executed notional ≤ daily limit ─────────────────────
    closing_qty = Decimal("0")
    clean_pos = Decimal(str(pos))
    if abs(clean_pos) < Decimal("0.0000001"):
        clean_pos = Decimal("0")
        
    if order.side == OrderSide.sell and clean_pos > 0:
        closing_qty = min(order.quantity, clean_pos)
    elif order.side == OrderSide.buy and clean_pos < 0:
        closing_qty = min(order.quantity, abs(clean_pos))

    closing_notional = closing_qty * cap_price
    notional_at_market = order.quantity * cap_price
    increasing_notional = notional_at_market - closing_notional

    if market_state is not None and increasing_notional > 0:
        projected_daily = market_state.today_executed_notional + increasing_notional
        if projected_daily > strategy_risk.max_daily_notional:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Order would bring today's total to {cur}{projected_daily:.2f}, "
                    f"exceeding the daily limit of {cur}{strategy_risk.max_daily_notional:.2f}."
                ),
                order_notional=safe_notional,
            )

    # ── Check 6: Platform-level order notional cap ────────────────────────────
    platform_cap_usd = Decimal(str(settings.default_max_order_notional))
    platform_cap = convert_amount(
        platform_cap_usd, PLATFORM_CAP_CURRENCY, strategy_risk.currency
    )
    if safe_notional > platform_cap:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional {cur}{safe_notional:.2f} exceeds platform-level cap {cur}{platform_cap:.2f}.",
            order_notional=safe_notional,
        )

    return RiskCheckResult(
        approved=True,
        reason="Order passed all risk checks.",
        order_notional=safe_notional,
    )
