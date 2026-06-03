from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.celery_app import celery_app
from app.db.repositories.runs import RunRepo
from app.db.repositories.strategies import StrategyRepo
from app.domain.models import (
    RunStatus,
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
        risk_raw = _json.loads(risk_raw)
    risk = StrategyRiskConfig.model_validate(risk_raw if isinstance(risk_raw, dict) else {})
    return StrategyResponse(
        id=str(record["id"]),
        tenant_id=str(record["tenant_id"]),
        owner_user_id=str(record["owner_user_id"]),
        name=record["name"],
        prompt=record["prompt"],
        symbols=list(record["symbols"]),
        timeframe=record["timeframe"],
        status=StrategyStatus(record["status"]),
        generated_logic=record["generated_logic"] or "",
        risk=risk,
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
    record = await repo.create(
        owner_user_id=current_user.user_id,
        name=request.name,
        prompt=request.prompt,
        symbols=[s.upper() for s in request.symbols],
        exchange="NASDAQ",
        timeframe=request.timeframe,
        creation_mode="nl",
        risk_config=request.risk.model_dump(mode="json"),
        generated_logic=compile_strategy_prompt(request),
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

    try:
        task = execute_trading_strategy.apply_async(
            args=[
                str(strategy_id),
                str(current_user.user_id),
                str(run["id"]),
                request.dry_run,
                list(record["symbols"]),
                dict(record["risk_config"]) if isinstance(record["risk_config"], dict) else {},
            ],
            queue="trading_tasks",
        )
    except Exception as exc:
        await run_repo.mark_failed(run["id"], str(exc))
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


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> TaskStatusResponse:
    result = celery_app.AsyncResult(task_id)
    payload = result.result if isinstance(result.result, dict) else None
    return TaskStatusResponse(task_id=task_id, celery_status=result.status, result=payload)
