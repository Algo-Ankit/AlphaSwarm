"""
Centralized risk verification. Called before EVERY broker API call.
This function is the safety wall. It must never be bypassed.
Adding a new check: add it here, not in strategy code.
"""
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.domain.market_data import MarketState
from app.domain.market_hours import is_market_open
from app.domain.models import OrderIntent, OrderSide, RiskCheckResult, StrategyRiskConfig


def verify_order_intent(
    order: OrderIntent,
    strategy_risk: StrategyRiskConfig,
    market_state: MarketState | None = None,
    settings: Settings | None = None,
    current_position: float | None = None,
    current_position_value: float | None = None,
    open_positions_count: int = 0,
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
    """
    settings = settings or get_settings()
    symbol = order.symbol.upper()
    notional = order.estimated_notional

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

    # ── Check 4: Order notional ≤ strategy limit ─────────────────────────────
    if notional > strategy_risk.max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional ${notional:.2f} exceeds strategy limit ${strategy_risk.max_order_notional:.2f}.",
            order_notional=notional,
        )

    # ── Check 4a: Per-symbol position notional cap ────────────────────────────
    if current_position_value is not None and order.side == OrderSide.buy:
        projected_position = Decimal(str(current_position_value)) + notional
        if projected_position > strategy_risk.max_position_notional:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Order would bring {symbol} exposure to ${projected_position:.2f}, "
                    f"exceeding the per-symbol position limit of ${strategy_risk.max_position_notional:.2f}."
                ),
                order_notional=notional,
            )

    # ── Check 4b: Max concurrent open positions ───────────────────────────────
    if (current_position is None or current_position == 0.0) and order.side == OrderSide.buy:
        if open_positions_count >= strategy_risk.max_open_positions:
            return RiskCheckResult(
                approved=False,
                reason=(
                    f"Strategy has {open_positions_count} open positions at the limit of "
                    f"{strategy_risk.max_open_positions}. Close an existing position before opening {symbol}."
                ),
                order_notional=notional,
            )

    # ── Check 5: Today's executed notional ≤ daily limit ─────────────────────
    # Only exempt genuinely risk-reducing trades (closing an open position).
    # A SELL when flat is a short sale — subject to the cap.
    # A BUY when flat is a new long — subject to the cap.
    # Exempting all SELLs (old behaviour) allowed unbounded short selling and
    # then trapped the strategy: the buy-to-cover would be blocked by the daily cap.
    pos = current_position or 0.0
    is_risk_reducing = (
        (order.side == OrderSide.sell and pos > 0) or   # closing a long
        (order.side == OrderSide.buy  and pos < 0)       # covering a short
    )
    if market_state is not None and not is_risk_reducing:
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
    platform_cap = Decimal(str(settings.default_max_order_notional))
    if notional > platform_cap:
        return RiskCheckResult(
            approved=False,
            reason=f"Order notional ${notional:.2f} exceeds platform-level cap ${platform_cap:.2f}.",
            order_notional=notional,
        )

    return RiskCheckResult(
        approved=True,
        reason="Order passed all risk checks.",
        order_notional=notional,
    )
