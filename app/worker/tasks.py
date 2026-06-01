import time

from app.core.celery_app import celery_app
from app.domain.models import OrderIntent, OrderSide, OrderType, StrategyRiskConfig
from app.domain.risk import verify_order_intent


@celery_app.task(name="app.worker.tasks.execute_trading_strategy")
def execute_trading_strategy(
    strategy_id: str,
    user_id: str,
    run_id: str | None = None,
    dry_run: bool = True,
    symbols: list[str] | None = None,
    risk_config: dict | None = None,
):
    """
    Isolated background task that runs a specific user's trading strategy.
    This runs asynchronously and does not block the FastAPI web server.
    """
    tradable_symbols = symbols or ["SPY"]
    risk_profile = StrategyRiskConfig.model_validate(
        risk_config or {"allowed_symbols": tradable_symbols}
    )
    candidate_order = OrderIntent(
        strategy_id=strategy_id,
        symbol=tradable_symbols[0].upper(),
        side=OrderSide.buy,
        quantity=1,
        order_type=OrderType.market,
        estimated_price=500,
    )
    risk_result = verify_order_intent(candidate_order, risk_profile)

    if not risk_result.approved:
        return {
            "status": "rejected",
            "run_id": run_id,
            "strategy_id": strategy_id,
            "user_id": user_id,
            "reason": risk_result.reason,
        }

    time.sleep(2)

    return {
        "status": "success",
        "run_id": run_id,
        "strategy_id": strategy_id,
        "user_id": user_id,
        "dry_run": dry_run,
        "broker_mode": "paper",
        "simulated_order": candidate_order.model_dump(mode="json"),
        "risk": risk_result.model_dump(mode="json"),
        "simulated_pnl": 0.0,
    }
