from threading import Lock
from uuid import uuid4

from app.domain.models import (
    RunStatus,
    StrategyCreateRequest,
    StrategyResponse,
    StrategyRunRecord,
)
from app.services.strategy_compiler import compile_strategy_prompt


class StrategyStore:
    def __init__(self) -> None:
        self._strategies: dict[str, StrategyResponse] = {}
        self._runs: dict[str, StrategyRunRecord] = {}
        self._lock = Lock()

    def create_strategy(
        self,
        tenant_id: str,
        owner_user_id: str,
        request: StrategyCreateRequest,
    ) -> StrategyResponse:
        strategy = StrategyResponse(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            name=request.name,
            prompt=request.prompt,
            symbols=[symbol.upper() for symbol in request.symbols],
            timeframe=request.timeframe,
            generated_logic=compile_strategy_prompt(request),
            risk=request.risk,
        )
        with self._lock:
            self._strategies[strategy.id] = strategy
        return strategy

    def list_strategies(self, tenant_id: str) -> list[StrategyResponse]:
        with self._lock:
            return [
                strategy
                for strategy in self._strategies.values()
                if strategy.tenant_id == tenant_id
            ]

    def get_strategy(self, tenant_id: str, strategy_id: str) -> StrategyResponse | None:
        with self._lock:
            strategy = self._strategies.get(strategy_id)
        if strategy and strategy.tenant_id == tenant_id:
            return strategy
        return None

    def create_run(
        self,
        tenant_id: str,
        strategy_id: str,
        dry_run: bool,
    ) -> StrategyRunRecord:
        run = StrategyRunRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            dry_run=dry_run,
        )
        with self._lock:
            self._runs[run.id] = run
        return run

    def mark_run_dispatched(self, run_id: str, task_id: str) -> StrategyRunRecord:
        with self._lock:
            run = self._runs[run_id]
            run.task_id = task_id
            run.status = RunStatus.queued
            self._runs[run_id] = run
        return run

    def mark_run_failed(self, run_id: str, error: str) -> StrategyRunRecord:
        with self._lock:
            run = self._runs[run_id]
            run.status = RunStatus.failed
            run.error = error
            self._runs[run_id] = run
        return run


strategy_store = StrategyStore()
