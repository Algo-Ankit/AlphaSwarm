from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.core.celery_app import celery_app
from app.domain.models import (
    RunStatus,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyRunRequest,
    StrategyRunResponse,
    TaskStatusResponse,
)
from app.services.strategy_store import strategy_store
from app.worker.tasks import execute_trading_strategy

router = APIRouter(prefix="/v1", tags=["strategies"])

TenantHeader = Annotated[str, Header(alias="X-Tenant-Id")]
UserHeader = Annotated[str, Header(alias="X-User-Id")]


@router.post(
    "/strategies",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy(
    request: StrategyCreateRequest,
    tenant_id: TenantHeader,
    user_id: UserHeader,
) -> StrategyResponse:
    return strategy_store.create_strategy(tenant_id, user_id, request)


@router.get("/strategies", response_model=list[StrategyResponse])
async def list_strategies(tenant_id: TenantHeader) -> list[StrategyResponse]:
    return strategy_store.list_strategies(tenant_id)


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: str, tenant_id: TenantHeader) -> StrategyResponse:
    strategy = strategy_store.get_strategy(tenant_id, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("/strategies/{strategy_id}/runs", response_model=StrategyRunResponse)
async def run_strategy(
    strategy_id: str,
    request: StrategyRunRequest,
    tenant_id: TenantHeader,
) -> StrategyRunResponse:
    strategy = strategy_store.get_strategy(tenant_id, strategy_id)
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    run = strategy_store.create_run(tenant_id, strategy_id, request.dry_run)
    try:
        task = execute_trading_strategy.apply_async(
            args=[
                strategy_id,
                strategy.owner_user_id,
                run.id,
                request.dry_run,
                strategy.symbols,
                strategy.risk.model_dump(mode="json"),
            ],
            queue="trading_tasks",
        )
    except Exception as exc:
        strategy_store.mark_run_failed(run.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not dispatch strategy run to Celery",
        ) from exc

    strategy_store.mark_run_dispatched(run.id, task.id)
    return StrategyRunResponse(
        run_id=run.id,
        strategy_id=strategy_id,
        task_id=task.id,
        status=RunStatus.queued,
        dry_run=request.dry_run,
        message="Strategy run dispatched to isolated worker queue",
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    result = celery_app.AsyncResult(task_id)
    payload = result.result if isinstance(result.result, dict) else None
    return TaskStatusResponse(task_id=task_id, celery_status=result.status, result=payload)
