from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Decimal that serializes to float in JSON/dict-mode so DB JSON columns and
# API responses receive numeric values, not strings.
JsonDecimal = Annotated[Decimal, PlainSerializer(float, when_used="json")]


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
    # frozen so sandbox strategies cannot mutate risk limits at runtime.
    model_config = ConfigDict(frozen=True)

    # ── Per-order ─────────────────────────────────────────────────────────────
    max_order_notional: JsonDecimal = Field(default=Decimal("1000"), gt=0)

    # ── Position limits ───────────────────────────────────────────────────────
    max_position_notional: JsonDecimal = Field(default=Decimal("10000"), gt=0)
    max_open_positions: int = Field(default=5, ge=1, le=100)

    # ── Daily gross turnover cap (buy + sell) ─────────────────────────────────
    max_daily_notional: JsonDecimal = Field(default=Decimal("50000"), gt=0)

    # ── Automated exit params — None = disabled ───────────────────────────────
    # float (not Decimal) so JSON serialization produces a number, not a string
    stop_loss_pct: float | None = Field(default=None, ge=0)
    take_profit_pct: float | None = Field(default=None, ge=0)

    # ── Execution cost model (informational, used in backtest P&L) ────────────
    slippage_bps: int = Field(default=5, ge=0, le=500)
    commission_per_share: JsonDecimal = Field(default=Decimal("0.005"), ge=0)

    # ── Session gate ──────────────────────────────────────────────────────────
    trade_session: Literal["regular", "extended"] = Field(default="regular")

    # ── Settlement currency ───────────────────────────────────────────────────
    # Notional limits above are denominated in this currency. Derived from the
    # strategy's exchange at creation (USD for US/crypto, INR for NSE/BSE) so a
    # ₹1000 limit is never confused with a $1000 limit. See app/domain/broker_routing.py.
    currency: str = Field(default="USD", max_length=8)

    # ── Existing ──────────────────────────────────────────────────────────────
    allowed_symbols: list[str] = Field(default_factory=lambda: ["SPY"])
    paper_trading_only: bool = True


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    prompt: str = Field(min_length=10, max_length=4_000)
    symbols: list[str] = Field(default_factory=lambda: ["SPY"], min_length=1)
    exchange: str | None = Field(default=None, max_length=20)
    timeframe: str = Field(default="1Min", max_length=20)
    risk: StrategyRiskConfig = Field(default_factory=StrategyRiskConfig)
    creation_mode: str = Field(default="nl", pattern="^(nl|quant)$")
    code_source: str | None = Field(default=None, max_length=50_000)
    llm_config_id: str | None = Field(default=None)


class StrategyResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    owner_user_id: str
    name: str
    prompt: str
    symbols: list[str]
    exchange: str = "NASDAQ"
    timeframe: str
    status: StrategyStatus = StrategyStatus.draft
    generated_logic: str
    explanation: str = ""  # plain-English summary (NL strategies); empty for quant/hand-written
    risk: StrategyRiskConfig
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StrategyCodeUpdateRequest(BaseModel):
    code_source: str = Field(min_length=20, max_length=50_000)


class StrategyRunRequest(BaseModel):
    dry_run: bool = True


class StrategyRunResponse(BaseModel):
    run_id: str
    strategy_id: str
    task_id: str
    status: RunStatus
    dry_run: bool
    message: str


class OrderIntent(BaseModel):
    strategy_id: str
    symbol: str
    exchange: str = "NASDAQ"
    side: OrderSide
    quantity: JsonDecimal = Field(gt=0)
    order_type: OrderType = OrderType.market
    estimated_price: JsonDecimal = Field(gt=0)
    limit_price: JsonDecimal | None = None
    stop_loss_price: JsonDecimal | None = None
    take_profit_price: JsonDecimal | None = None
    is_paper: bool = True  # Must be explicitly False to attempt live order

    @property
    def estimated_notional(self) -> Decimal:
        # Use limit_price for risk sizing on limit orders — estimated_price may be stale
        price = (
            self.limit_price
            if self.order_type == OrderType.limit and self.limit_price is not None
            else self.estimated_price
        )
        return self.quantity * price


class RiskCheckResult(BaseModel):
    approved: bool
    reason: str
    order_notional: JsonDecimal


class OrderResult(BaseModel):
    order_id: str | None = None           # broker order ID; None for dry runs
    symbol: str
    side: OrderSide
    quantity: JsonDecimal
    fill_price: JsonDecimal | None = None
    estimated_price: JsonDecimal
    broker_status: str                     # filled | pending | dry_run | rejected
    is_paper: bool
    created_at: datetime = Field(default_factory=utc_now)


class TaskStatusResponse(BaseModel):
    task_id: str
    celery_status: str
    result: dict | None = None


# ── Phase 5: Backtest ─────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    exchange: str = "NASDAQ"
    timeframe: str = "1d"
    limit: int = Field(default=252, ge=20, le=1000)
    initial_equity: float = Field(default=10_000.0, gt=0)
    start_date: datetime | None = None
    end_date: datetime | None = None


class BacktestTradeRecord(BaseModel):
    bar_index: int
    timestamp: datetime
    symbol: str
    side: str
    quantity: JsonDecimal
    price: JsonDecimal


class BacktestBarRecord(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BacktestMetricsModel(BaseModel):
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    profitable_trades: int
    initial_equity: float
    final_equity: float
    # Extended risk-adjusted + benchmark metrics (default-safe for older persisted rows)
    sortino_ratio: float = 0.0
    cagr_pct: float = 0.0
    calmar_ratio: float = 0.0
    profit_factor: float = 0.0
    benchmark_return_pct: float = 0.0
    alpha_vs_benchmark_pct: float = 0.0


class BacktestResponse(BaseModel):
    strategy_id: str
    symbol: str
    timeframe: str
    bars_processed: int
    bars: list[BacktestBarRecord]
    trades: list[BacktestTradeRecord]
    equity_curve: list[float]
    metrics: BacktestMetricsModel
    started_at: datetime
    completed_at: datetime


class BacktestSummary(BaseModel):
    ran_at: datetime
    symbol: str
    exchange: str
    timeframe: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
