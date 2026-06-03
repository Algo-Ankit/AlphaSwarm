from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyStatus(str, Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    rejected = "rejected"


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, Enum):
    market = "market"
    limit = "limit"


class StrategyRiskConfig(BaseModel):
    max_order_notional: float = Field(default=1_000.0, gt=0)
    max_daily_notional: float = Field(default=5_000.0, gt=0)
    allowed_symbols: list[str] = Field(default_factory=lambda: ["SPY"])
    paper_trading_only: bool = True


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    prompt: str = Field(min_length=10, max_length=4_000)
    symbols: list[str] = Field(default_factory=lambda: ["SPY"])
    timeframe: str = Field(default="1Min", max_length=20)
    risk: StrategyRiskConfig = Field(default_factory=StrategyRiskConfig)
    creation_mode: str = Field(default="nl", pattern="^(nl|quant)$")
    code_source: str | None = Field(default=None, max_length=50_000)


class StrategyResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    owner_user_id: str
    name: str
    prompt: str
    symbols: list[str]
    timeframe: str
    status: StrategyStatus = StrategyStatus.draft
    generated_logic: str
    risk: StrategyRiskConfig
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StrategyRunRequest(BaseModel):
    dry_run: bool = True


class StrategyRunResponse(BaseModel):
    run_id: str
    strategy_id: str
    task_id: str
    status: RunStatus
    dry_run: bool
    message: str


class StrategyRunRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    strategy_id: str
    task_id: str | None = None
    status: RunStatus = RunStatus.queued
    dry_run: bool = True
    error: str | None = None
    result: dict | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OrderIntent(BaseModel):
    strategy_id: str
    symbol: str
    exchange: str = "NASDAQ"
    side: OrderSide
    quantity: float = Field(gt=0)
    order_type: OrderType = OrderType.market
    estimated_price: float = Field(gt=0)
    limit_price: float | None = None
    is_paper: bool = True  # Must be explicitly False to attempt live order

    @property
    def estimated_notional(self) -> float:
        return self.quantity * self.estimated_price


class RiskCheckResult(BaseModel):
    approved: bool
    reason: str
    order_notional: float


class TaskStatusResponse(BaseModel):
    task_id: str
    celery_status: str
    result: dict | None = None
