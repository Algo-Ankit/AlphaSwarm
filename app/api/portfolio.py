"""
Portfolio API — GET /summary (latest snapshot) + GET /snapshots (equity curve).

Snapshots are written every 5 min by app.worker.beat_tasks.snapshot_portfolio,
which also publishes a live update to /v1/ws/portfolio. The platform never holds
funds — total_equity/open_pnl are display aggregates derived from positions and
the user's own broker account; cash_balance is a nullable display snapshot.
"""

from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.portfolio import PortfolioRepo
from app.db.repositories.unified_holdings import UnifiedHoldingsRepo
from app.services.forecasting import run_monte_carlo
from app.services.portfolio_parser import parse_cas, summarize
from app.services.portfolio_risk import analyze_holdings

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])

# Asset class label by exchange
_ASSET_CLASS: dict[str, str] = {
    "NASDAQ": "Equity (US)",
    "NYSE": "Equity (US)",
    "NSE": "Equity (IN)",
    "BSE": "Equity (IN)",
    "CRYPTO": "Crypto",
}
_ALLOC_COLOR: dict[str, str] = {
    "Equity (US)": "#8b5cf6",
    "Equity (IN)": "#06b6d4",
    "Crypto": "#f59e0b",
    "Other": "#6b7280",
}


class PortfolioSummary(BaseModel):
    snapshot_time: str | None
    total_equity: float
    open_pnl: float
    realized_pnl_today: float
    active_strategies: int
    has_data: bool


class SnapshotPoint(BaseModel):
    snapshot_time: str
    total_equity: float
    open_pnl: float
    realized_pnl_today: float
    active_strategies: int


@router.get("/allocation")
async def get_allocation(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[dict]:
    """
    Return asset allocation breakdown by exchange/asset class.
    Derived from the positions table (open positions only).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT exchange,
                   SUM(quantity * COALESCE(current_price, avg_cost)) AS notional
            FROM positions
            WHERE tenant_id = $1 AND quantity > 0
            GROUP BY exchange
            """,
            current_user.tenant_id,
        )

    buckets: dict[str, float] = {}
    for row in rows:
        label = _ASSET_CLASS.get(row["exchange"].upper(), "Other")
        buckets[label] = buckets.get(label, 0.0) + float(row["notional"] or 0)

    total = sum(buckets.values()) or 1.0
    return [
        {
            "label": label,
            "value": round(value, 2),
            "pct": round(value / total * 100, 1),
            "color": _ALLOC_COLOR.get(label, _ALLOC_COLOR["Other"]),
        }
        for label, value in buckets.items()
        if value > 0
    ]


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> PortfolioSummary:
    repo = PortfolioRepo(pool, current_user.tenant_id)
    row = await repo.latest()
    if not row:
        return PortfolioSummary(
            snapshot_time=None,
            total_equity=0.0,
            open_pnl=0.0,
            realized_pnl_today=0.0,
            active_strategies=0,
            has_data=False,
        )
    return PortfolioSummary(
        snapshot_time=row["snapshot_time"].isoformat(),
        total_equity=float(row["total_equity"]),
        open_pnl=float(row["open_pnl"]),
        realized_pnl_today=float(row["realized_pnl_today"]),
        active_strategies=int(row["active_strategies"]),
        has_data=True,
    )


@router.get("/snapshots", response_model=list[SnapshotPoint])
async def get_snapshots(
    limit: int = Query(200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[SnapshotPoint]:
    repo = PortfolioRepo(pool, current_user.tenant_id)
    rows = await repo.history(limit=limit)
    return [
        SnapshotPoint(
            snapshot_time=r["snapshot_time"].isoformat(),
            total_equity=float(r["total_equity"]),
            open_pnl=float(r["open_pnl"]),
            realized_pnl_today=float(r["realized_pnl_today"]),
            active_strategies=int(r["active_strategies"]),
        )
        for r in rows
    ]


# ── Unified multi-broker holdings (CAS ingestion) ──────────────────────────────


class CasHolding(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    name: str = ""
    isin: str | None = None
    asset_class: str = "equity"  # equity | mutual_fund | etf | bond | other
    broker: str = "Unknown"  # depository participant / broker
    quantity: float = Field(gt=0)
    avg_cost: float = Field(ge=0, default=0)
    current_price: float | None = None


class CasUploadRequest(BaseModel):
    statement_date: date | None = None
    holdings: list[CasHolding] = Field(default_factory=list)


class UnifiedHolding(BaseModel):
    isin: str | None
    symbol: str
    name: str
    asset_class: str
    broker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    current_value: float


class UnifiedPortfolioResponse(BaseModel):
    statement_date: str | None
    holdings_count: int
    total_value: float
    total_cost: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    by_broker: dict[str, float]
    by_asset_class: dict[str, float]
    holdings: list[UnifiedHolding]


def _record_to_holding(r: asyncpg.Record) -> UnifiedHolding:
    cp = r["current_price"]
    return UnifiedHolding(
        isin=r["isin"],
        symbol=r["symbol"],
        name=r["name"],
        asset_class=r["asset_class"],
        broker=r["broker"],
        quantity=float(r["quantity"]),
        avg_cost=float(r["avg_cost"]),
        current_price=float(cp) if cp is not None else None,
        current_value=float(r["current_value"]),
    )


@router.post("/upload-cas", response_model=UnifiedPortfolioResponse)
async def upload_cas(
    request: CasUploadRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> UnifiedPortfolioResponse:
    """
    Ingest a (simulated) parsed NSDL/CDSL Consolidated Account Statement.
    Replaces the tenant's prior holdings with this statement's snapshot.
    """
    try:
        parsed = parse_cas([h.model_dump() for h in request.holdings])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    repo = UnifiedHoldingsRepo(pool, current_user.tenant_id)
    await repo.replace_all(parsed, request.statement_date)
    return await _build_unified_response(repo, request.statement_date)


@router.get("/unified", response_model=UnifiedPortfolioResponse)
async def get_unified(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> UnifiedPortfolioResponse:
    """Consolidated view of all imported multi-broker holdings."""
    repo = UnifiedHoldingsRepo(pool, current_user.tenant_id)
    return await _build_unified_response(repo, None)


async def _build_unified_response(
    repo: UnifiedHoldingsRepo, statement_date: date | None
) -> UnifiedPortfolioResponse:
    rows = await repo.list_all()
    # Re-summarise from the persisted rows so the response is consistent whether it
    # follows an upload or a plain read. statement_date is read off the rows.
    parsed = [
        {
            "symbol": r["symbol"],
            "asset_class": r["asset_class"],
            "broker": r["broker"],
            "quantity": r["quantity"],
            "avg_cost": r["avg_cost"],
            "current_value": r["current_value"],
        }
        for r in rows
    ]
    row_date = rows[0]["statement_date"] if rows else None
    summary = summarize(parsed, statement_date or row_date)
    return UnifiedPortfolioResponse(
        **summary,
        holdings=[_record_to_holding(r) for r in rows],
    )


# ── Holdings risk review (deterministic + optional AI narrative) ───────────────


class HoldingRisk(BaseModel):
    symbol: str
    name: str
    broker: str
    value: float
    weight_pct: float
    unrealized_pnl_pct: float | None
    signal: str  # Trim | Review | Hold
    reasons: list[str]


class RiskReviewResponse(BaseModel):
    total_value: float
    holdings_count: int
    concentration_index: float
    top_weight_pct: float
    broker_concentration_pct: float
    asset_class_concentration_pct: float
    diversification: str  # diversified | moderate | concentrated | unknown
    flagged_count: int
    verdict: str
    holdings: list[HoldingRisk]
    # Present only when include_ai=true and the user has a usable BYOK key.
    ai_narrative: str | None = None
    ai_available: bool = False
    ai_error: str | None = None


@router.get("/risk-review", response_model=RiskReviewResponse)
async def risk_review(
    include_ai: bool = Query(False, description="Also generate a plain-English AI narrative"),
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> RiskReviewResponse:
    """
    Real-time risk scorecard over the user's consolidated holdings: concentration,
    drawdown and diversification signals per position (Trim / Review / Hold). The
    deterministic analysis always runs; when include_ai is set we layer the BYOK
    AI advisor on top for a narrative — best-effort, never blocking the scorecard.
    """
    repo = UnifiedHoldingsRepo(pool, current_user.tenant_id)
    rows = await repo.list_all()
    holdings = [
        {
            "symbol": r["symbol"],
            "name": r["name"],
            "broker": r["broker"],
            "asset_class": r["asset_class"],
            "quantity": float(r["quantity"]),
            "avg_cost": float(r["avg_cost"]),
            "current_price": float(r["current_price"]) if r["current_price"] is not None else None,
            "current_value": float(r["current_value"]),
        }
        for r in rows
    ]
    risk = analyze_holdings(holdings)

    ai_narrative: str | None = None
    ai_available = False
    ai_error: str | None = None
    if include_ai and risk["holdings"]:
        from app.services.ai_advisor import review_holdings

        try:
            ai_narrative = await review_holdings(risk, current_user, pool=pool)
            ai_available = True
        except ValueError as exc:
            # BYOK missing or model error — the scorecard is still returned.
            ai_error = str(exc)

    return RiskReviewResponse(
        **{k: risk[k] for k in risk if k != "holdings"},
        holdings=[HoldingRisk(**h) for h in risk["holdings"]],
        ai_narrative=ai_narrative,
        ai_available=ai_available,
        ai_error=ai_error,
    )


# ── Monte Carlo wealth forecast ────────────────────────────────────────────────


class ForecastRequest(BaseModel):
    current_portfolio_value: float = Field(ge=0)
    monthly_contribution: float = Field(ge=0, description="Monthly SIP amount")
    expected_cagr: float = Field(description="Annual CAGR as a fraction, e.g. 0.12 for 12%")
    annual_volatility: float = Field(ge=0, description="Annual volatility as a fraction")
    years_to_forecast: int = Field(ge=1, le=40)
    simulations: int = Field(default=1000, ge=1000, le=50000)


@router.post("/forecast")
async def forecast(
    request: ForecastRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Run a Monte Carlo (GBM) wealth projection — P10/P50/P90 per year."""
    try:
        result = run_monte_carlo(
            current_portfolio_value=request.current_portfolio_value,
            monthly_contribution=request.monthly_contribution,
            expected_cagr=request.expected_cagr,
            annual_volatility=request.annual_volatility,
            years_to_forecast=request.years_to_forecast,
            simulations=request.simulations,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return result.to_dict()
