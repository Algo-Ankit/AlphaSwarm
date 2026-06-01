from app.core.config import Settings, get_settings
from app.domain.models import OrderIntent, RiskCheckResult, StrategyRiskConfig


def verify_order_intent(
    order: OrderIntent,
    strategy_risk: StrategyRiskConfig,
    settings: Settings | None = None,
) -> RiskCheckResult:
    settings = settings or get_settings()
    symbol = order.symbol.upper()
    allowed_by_platform = settings.allowed_symbol_set
    allowed_by_strategy = {item.upper() for item in strategy_risk.allowed_symbols}
    order_notional = order.estimated_notional

    if symbol not in allowed_by_platform:
        return RiskCheckResult(
            approved=False,
            reason=f"{symbol} is not enabled at the platform level",
            order_notional=order_notional,
        )

    if symbol not in allowed_by_strategy:
        return RiskCheckResult(
            approved=False,
            reason=f"{symbol} is not allowed by this strategy risk profile",
            order_notional=order_notional,
        )

    if order_notional > settings.max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason="order exceeds platform max order notional",
            order_notional=order_notional,
        )

    if order_notional > strategy_risk.max_order_notional:
        return RiskCheckResult(
            approved=False,
            reason="order exceeds strategy max order notional",
            order_notional=order_notional,
        )

    return RiskCheckResult(
        approved=True,
        reason="order passed centralized risk verification",
        order_notional=order_notional,
    )
