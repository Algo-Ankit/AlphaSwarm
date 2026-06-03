import time
from decimal import Decimal

from app.core.celery_app import celery_app
from app.domain.models import OrderIntent, OrderSide, OrderType, StrategyRiskConfig
from app.domain.risk import verify_order_intent
from app.worker.run_logger import RunLogger


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
    Isolated background task that runs a trading strategy.
    Phase 4 will replace the stub signal with a real on_bar() loop.
    All log.* calls stream to the browser terminal in real time via Redis pub/sub.
    """
    log = RunLogger(run_id) if run_id else None

    try:
        tradable_symbols = symbols or ["SPY"]
        symbol = tradable_symbols[0].upper()

        if log:
            log.status("running")
            log.info(
                f"Worker started — strategy {strategy_id[:8]}",
                symbols=tradable_symbols,
                dry_run=dry_run,
                mode="paper" if dry_run else "live",
            )

        # ── Load risk profile ─────────────────────────────────────────────────
        risk_profile = StrategyRiskConfig.model_validate(
            risk_config or {"allowed_symbols": tradable_symbols}
        )
        if log:
            log.info(
                f"Risk profile loaded — "
                f"max order ${risk_profile.max_order_notional:.0f}  "
                f"daily limit ${risk_profile.max_daily_notional:.0f}  "
                f"symbols {risk_profile.allowed_symbols}"
            )

        # ── Phase 4 placeholder: fetch bars + run on_bar() ───────────────────
        # Currently emits a synthetic BUY signal for demonstration.
        # Phase 4 replaces this block with the real BaseStrategy loop.
        if log:
            log.info(f"Fetching latest bar for {symbol}…")

        time.sleep(0.5)  # simulate bar fetch latency

        estimated_price = Decimal("523.47")  # placeholder until real market data
        quantity = Decimal("1")

        if log:
            log.signal(
                f"Signal → BUY {symbol}  qty={quantity}  "
                f"price≈${estimated_price}  notional=${quantity * estimated_price:.2f}",
                side="buy",
                symbol=symbol,
                quantity=str(quantity),
                estimated_price=str(estimated_price),
            )

        # ── Risk check ───────────────────────────────────────────────────────
        candidate_order = OrderIntent(
            strategy_id=strategy_id,
            symbol=symbol,
            side=OrderSide.buy,
            quantity=quantity,
            order_type=OrderType.market,
            estimated_price=estimated_price,
        )
        risk_result = verify_order_intent(candidate_order, risk_profile)

        if not risk_result.approved:
            if log:
                log.risk(f"REJECTED — {risk_result.reason}")
                log.status("rejected", risk_result.reason)
            return {
                "status": "rejected",
                "run_id": run_id,
                "strategy_id": strategy_id,
                "user_id": user_id,
                "reason": risk_result.reason,
            }

        if log:
            log.risk(
                f"PASSED — notional ${risk_result.order_notional:.2f} "
                f"within limits"
            )

        # ── Order placement ───────────────────────────────────────────────────
        time.sleep(1.0)  # simulate order round-trip

        if dry_run:
            if log:
                log.order(
                    f"[DRY RUN] BUY {symbol} × {quantity} — market order "
                    f"@ ~${estimated_price}  (no real order placed)"
                )
                log.info("Paper trade recorded — P&L tracking in Phase 4")
        else:
            if log:
                log.order(
                    f"LIVE order submitted: BUY {symbol} × {quantity} — market"
                )

        if log:
            log.status("completed", "Strategy run finished successfully")

        return {
            "status": "success",
            "run_id": run_id,
            "strategy_id": strategy_id,
            "user_id": user_id,
            "dry_run": dry_run,
            "broker_mode": "paper" if dry_run else "live",
            "simulated_order": candidate_order.model_dump(mode="json"),
            "risk": risk_result.model_dump(mode="json"),
            "simulated_pnl": 0.0,
        }

    except Exception as exc:
        if log:
            log.error(f"Worker exception: {exc}")
            log.status("failed", str(exc))
        raise

    finally:
        if log:
            log.close()
