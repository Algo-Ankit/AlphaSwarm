from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.celery_app import celery_app
from app.db.repositories.runs import RunRepo
from app.db.repositories.strategies import StrategyRepo
from app.domain.models import (
    RunStatus,
    StrategyCodeUpdateRequest,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyRiskConfig,
    StrategyRunRequest,
    StrategyRunResponse,
    StrategyStatus,
    TaskStatusResponse,
)
from app.services.strategy_compiler import compile_strategy_prompt
from app.worker.tasks import execute_trading_strategy

router = APIRouter(prefix="/v1", tags=["strategies"])


def _record_to_response(record: asyncpg.Record) -> StrategyResponse:
    import json as _json
    risk_raw = record["risk_config"]
    if isinstance(risk_raw, str):
        try:
            risk_raw = _json.loads(risk_raw)
        except Exception:
            risk_raw = {}
    try:
        risk = StrategyRiskConfig.model_validate(risk_raw if isinstance(risk_raw, dict) else {})
    except Exception:
        risk = StrategyRiskConfig()
        
    try:
        status_val = StrategyStatus(record["status"])
    except Exception:
        status_val = StrategyStatus.draft

    sip_amount = record.get("sip_monthly_amount")
    return StrategyResponse(
        id=str(record["id"]),
        tenant_id=str(record["tenant_id"]),
        owner_user_id=str(record["owner_user_id"]),
        name=record["name"],
        prompt=record["prompt"],
        symbols=list(record["symbols"]),
        exchange=record["exchange"],
        timeframe=record["timeframe"],
        status=status_val,
        generated_logic=record["generated_logic"] or "",
        explanation=record.get("explanation") or "",
        risk=risk,
        sip_paused=bool(record.get("sip_paused", False)),
        sip_monthly_amount=float(sip_amount) if sip_amount is not None else None,
        sip_frequency=record.get("sip_frequency") or "monthly",
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@router.post(
    "/strategies",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy(
    request: StrategyCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyResponse:
    repo = StrategyRepo(pool, current_user.tenant_id)
    if request.creation_mode == "quant":
        if not request.code_source or len(request.code_source.strip()) < 20:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="code_source is required for quant strategies")
        from app.services.strategy_sandbox import SandboxError, compile_strategy_code, normalize_strategy_code
        normalized = normalize_strategy_code(request.code_source)
        try:
            compile_strategy_code(normalized)
        except SandboxError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Strategy code failed sandbox validation: {exc}",
            ) from exc
        generated_logic = normalized
        explanation = ""  # hand-written code needs no AI explanation
        prompt_text = f"[quant] {request.name}"
    else:
        try:
            generated_logic, explanation = await compile_strategy_prompt(request, pool=pool)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        prompt_text = request.prompt

    if request.exchange:
        inferred_exchange = request.exchange.upper()
    else:
        primary_symbol = request.symbols[0].upper() if request.symbols else "SPY"
        if "-" in primary_symbol or "/" in primary_symbol:
            inferred_exchange = "CRYPTO"
        elif primary_symbol.endswith(".NS"):
            inferred_exchange = "NSE"
        elif primary_symbol.endswith(".BO"):
            inferred_exchange = "BSE"
        else:
            inferred_exchange = "NASDAQ"

    # Currency is a property of the market, not a user choice — derive it from the
    # exchange so notional limits are stored/displayed in ₹ for NSE/BSE, $ for US.
    from app.domain.broker_routing import currency_for_exchange
    risk_config = request.risk.model_dump(mode="json")
    risk_config["currency"] = currency_for_exchange(inferred_exchange)

    record = await repo.create(
        owner_user_id=current_user.user_id,
        name=request.name,
        prompt=prompt_text,
        symbols=[s.upper() for s in request.symbols],
        exchange=inferred_exchange,
        timeframe=request.timeframe,
        creation_mode=request.creation_mode,
        risk_config=risk_config,
        generated_logic=generated_logic,
        explanation=explanation,
    )
    return _record_to_response(record)


@router.get("/strategies", response_model=list[StrategyResponse])
async def list_strategies(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[StrategyResponse]:
    repo = StrategyRepo(pool, current_user.tenant_id)
    records = await repo.list_all()
    return [_record_to_response(r) for r in records]


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyResponse:
    repo = StrategyRepo(pool, current_user.tenant_id)
    record = await repo.get_by_id(strategy_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return _record_to_response(record)


@router.patch(
    "/strategies/{strategy_id}/code",
    response_model=StrategyResponse,
    status_code=status.HTTP_200_OK,
)
async def update_strategy_code(
    strategy_id: UUID,
    request: StrategyCodeUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyResponse:
    from app.services.strategy_sandbox import SandboxError, compile_strategy_code, normalize_strategy_code
    normalized = normalize_strategy_code(request.code_source)
    try:
        compile_strategy_code(normalized)
    except SandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Strategy code failed sandbox validation: {exc}",
        ) from exc

    repo = StrategyRepo(pool, current_user.tenant_id)
    record = await repo.update_logic(strategy_id, normalized, current_user.user_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return _record_to_response(record)


@router.post("/strategies/{strategy_id}/runs", response_model=StrategyRunResponse)
async def run_strategy(
    strategy_id: UUID,
    request: StrategyRunRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyRunResponse:
    strategy_repo = StrategyRepo(pool, current_user.tenant_id)
    run_repo = RunRepo(pool, current_user.tenant_id)

    record = await strategy_repo.get_by_id(strategy_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    version_id = record["current_version_id"]
    run = await run_repo.create(
        strategy_id=strategy_id,
        version_id=version_id,
        dry_run=request.dry_run,
    )

    # asyncpg may return JSONB columns as str; parse defensively before dispatch
    import json as _json
    _rc = record["risk_config"]
    if isinstance(_rc, str):
        try:
            _rc = _json.loads(_rc)
        except Exception:
            _rc = {}
    risk_cfg_dict = _rc if isinstance(_rc, dict) else {}

    if risk_cfg_dict.get("paper_trading_only", True) and not request.dry_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This strategy is restricted to paper trading only by its risk configuration.",
        )

    # ── Billing gate: live agents require an active Quant Tier subscription ──
    # Paper/backtest runs (dry_run) are always free. Live deployment is the
    # monetised action, so it is blocked unless the tenant's Stripe subscription
    # is active/trialing.
    if not request.dry_run:
        from app.db.repositories.users import TenantRepo
        from app.services.billing import is_active_status

        tenant = await TenantRepo(pool).get_by_id(current_user.tenant_id)
        if not tenant or not is_active_status(tenant.get("subscription_status")):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    "Live agent deployment requires an active Quant Tier subscription. "
                    "Upgrade in Billing, or run this strategy in paper mode (dry_run=true)."
                ),
            )

    try:
        task = execute_trading_strategy.apply_async(
            args=[
                str(strategy_id),
                str(current_user.tenant_id),
                str(current_user.user_id),
                str(run["id"]),
                request.dry_run,
                list(record["symbols"]),
                str(record.get("timeframe") or "1d"),
                risk_cfg_dict,
            ],
            queue="trading_tasks",
        )
    except Exception as exc:
        try:
            await run_repo.mark_failed(run["id"], str(exc))
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not dispatch strategy run to Celery",
        ) from exc

    await run_repo.mark_dispatched(run["id"], task.id)
    return StrategyRunResponse(
        run_id=str(run["id"]),
        strategy_id=str(strategy_id),
        task_id=task.id,
        status=RunStatus.queued,
        dry_run=request.dry_run,
        message="Strategy run dispatched to isolated worker queue",
    )


class SipUpdateRequest(BaseModel):
    paused: bool


class LumpSumRequest(BaseModel):
    amount: float = Field(gt=0, description="Cash amount to inject (in the strategy's currency)")


@router.patch("/strategies/{strategy_id}/sip", response_model=StrategyResponse)
async def update_sip(
    strategy_id: UUID,
    body: SipUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> StrategyResponse:
    """Pause or resume the Systematic Investment Plan for a strategy."""
    repo = StrategyRepo(pool, current_user.tenant_id)
    record = await repo.get_by_id(strategy_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    await repo.update_sip_paused(strategy_id, body.paused)
    updated = await repo.get_by_id(strategy_id)
    return _record_to_response(updated)


@router.post("/strategies/{strategy_id}/lump-sum")
async def lump_sum_boost(
    strategy_id: UUID,
    body: LumpSumRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Request a one-off lump-sum cash injection for a strategy.
    Creates a rebalance_approval notification — the AI will not rebalance
    until the user explicitly clicks Approve in the notification center.
    """
    from app.db.repositories.notifications import NotificationRepo
    repo = StrategyRepo(pool, current_user.tenant_id)
    record = await repo.get_by_id(strategy_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    notif_repo = NotificationRepo(pool, current_user.tenant_id)
    notif = await notif_repo.create(
        user_id=current_user.user_id,
        type="rebalance_approval",
        title="Lump-Sum Rebalance Pending Approval",
        body=(
            f"A lump-sum boost of {body.amount:,.2f} has been queued for "
            f"'{record['name']}'. Review and click Approve to execute the rebalance."
        ),
        entity_type="strategy",
        entity_id=strategy_id,
    )

    # Mirror the in-app notification to email so the user can act on the
    # rebalance approval without being logged in (no-op if SendGrid unconfigured).
    from app.services.email import send_rebalance_approval_email
    await send_rebalance_approval_email(
        current_user.email, record["name"], notif["body"],
    )

    return {"notification_id": str(notif["id"]), "status": "pending_approval"}


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TaskStatusResponse:
    # Verify the task belongs to a run owned by this tenant (IDOR prevention)
    run = await pool.fetchrow(
        "SELECT id FROM strategy_runs WHERE celery_task_id = $1 AND tenant_id = $2",
        task_id, current_user.tenant_id,
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    result = celery_app.AsyncResult(task_id)
    payload = result.result if isinstance(result.result, dict) else None
    return TaskStatusResponse(task_id=task_id, celery_status=result.status, result=payload)
