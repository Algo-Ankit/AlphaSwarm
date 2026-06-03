"""
Forecast service — Prophet + ARIMA ensemble.
Computes N-day price forecast with 80% confidence intervals.
Results cached in `forecasts` table (stale after 1 hour).
CPU-heavy Prophet/ARIMA computation runs in a thread pool.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import asyncpg
import numpy as np
import pandas as pd

from app.db.repositories.intelligence import ForecastRepo

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=1)
_VALIDATION_WINDOW = 30  # days held out for MAE/MAPE


@dataclass
class ForecastPoint:
    date: str
    yhat: float
    yhat_lower: float
    yhat_upper: float


@dataclass
class ForecastResult:
    symbol: str
    exchange: str
    generated_at: str
    horizon_days: int
    model: str
    mae: float | None
    mape: float | None
    forecast: list[ForecastPoint]
    disclaimer: str = "Statistical projection — not financial advice."

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "generated_at": self.generated_at,
            "horizon_days": self.horizon_days,
            "model": self.model,
            "mae": self.mae,
            "mape": self.mape,
            "forecast": [
                {
                    "date": p.date,
                    "yhat": p.yhat,
                    "yhat_lower": p.yhat_lower,
                    "yhat_upper": p.yhat_upper,
                }
                for p in self.forecast
            ],
            "disclaimer": self.disclaimer,
        }


def _silence_prophet_logging() -> None:
    import logging as _log
    for name in ("prophet", "cmdstanpy", "pystan"):
        _log.getLogger(name).setLevel(_log.ERROR)


def _run_prophet(
    df: pd.DataFrame, horizon: int
) -> tuple[list[dict], float | None, float | None]:
    """Returns (forecast_points, mae, mape). df must have columns: ds, y."""
    _silence_prophet_logging()
    from prophet import Prophet

    cutoff = df["ds"].max() - pd.Timedelta(days=_VALIDATION_WINDOW)
    train = df[df["ds"] <= cutoff].copy()

    mae = mape = None
    if len(train) >= 20:
        m_val = Prophet(
            interval_width=0.80,
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            uncertainty_samples=0,
        )
        m_val.fit(train)
        val_df = df[df["ds"] > cutoff].copy()
        if len(val_df) >= 5:
            val_future = m_val.make_future_dataframe(periods=len(val_df), freq="B")
            val_fc = m_val.predict(val_future)
            predicted = val_fc.tail(len(val_df))["yhat"].values
            actual = val_df["y"].values[: len(predicted)]
            errors = np.abs(actual - predicted)
            mae = float(np.mean(errors))
            nonzero = actual != 0
            if nonzero.any():
                mape = float(
                    np.mean(np.abs(errors[nonzero] / actual[nonzero])) * 100
                )

    m_full = Prophet(
        interval_width=0.80,
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        uncertainty_samples=0,
    )
    m_full.fit(df)
    future = m_full.make_future_dataframe(periods=horizon, freq="B")
    fc = m_full.predict(future)
    tail = fc.tail(horizon)

    points = [
        {
            "date": row["ds"].strftime("%Y-%m-%d"),
            "yhat": round(float(row["yhat"]), 4),
            "yhat_lower": round(float(row["yhat_lower"]), 4),
            "yhat_upper": round(float(row["yhat_upper"]), 4),
        }
        for _, row in tail.iterrows()
    ]
    return points, mae, mape


def _run_arima(series: pd.Series, horizon: int) -> list[float]:
    """
    ARIMA(5,1,0) point forecast.
    Raises on convergence failure — caller decides whether to degrade gracefully.
    """
    from statsmodels.tsa.arima.model import ARIMA

    model = ARIMA(series, order=(5, 1, 0))
    fit = model.fit()
    return [round(float(v), 4) for v in fit.forecast(steps=horizon)]


def _compute_ensemble_sync(
    close_prices: list[tuple[datetime, float]], horizon: int
) -> tuple[list[dict], float | None, float | None]:
    """
    Runs Prophet + ARIMA in the current thread, returns ensemble forecast.
    Called via asyncio.to_thread() — never call directly from async context.
    """
    df = pd.DataFrame(close_prices, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    df = df.sort_values("ds").drop_duplicates("ds")

    if len(df) < 30:
        raise ValueError(
            f"Insufficient price history: {len(df)} bars (need ≥ 30)"
        )

    prophet_points, mae, mape = _run_prophet(df, horizon)

    try:
        arima_preds = _run_arima(df["y"], horizon)
    except Exception as exc:
        # ARIMA failed (non-stationary series, convergence issue, etc.)
        # Use Prophet-only rather than averaging with a fake flat line.
        logger.warning(
            "ARIMA convergence failed (%s) — degrading to Prophet-only forecast", exc
        )
        return prophet_points, "prophet", mae, mape

    # Ensemble: average Prophet + ARIMA yhats; shift CI bands by same delta
    ensemble: list[dict] = []
    for i, pt in enumerate(prophet_points):
        arima_val = arima_preds[i] if i < len(arima_preds) else pt["yhat"]
        ens_yhat = round((pt["yhat"] + arima_val) / 2.0, 4)
        delta = ens_yhat - pt["yhat"]
        ensemble.append(
            {
                "date": pt["date"],
                "yhat": ens_yhat,
                "yhat_lower": round(pt["yhat_lower"] + delta, 4),
                "yhat_upper": round(pt["yhat_upper"] + delta, 4),
            }
        )

    return ensemble, "ensemble", mae, mape


async def get_forecast(
    symbol: str,
    exchange: str,
    horizon_days: int,
    pool: asyncpg.Pool,
) -> ForecastResult:
    repo = ForecastRepo(pool)
    sym = symbol.upper()
    exch = exchange.upper()

    cached = await repo.get_latest(sym, exch, horizon_days)
    if cached:
        gen_at = cached["generated_at"]
        if gen_at.tzinfo is None:
            gen_at = gen_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - gen_at
        if age < _CACHE_TTL:
            points = [ForecastPoint(**p) for p in cached["forecast_json"]]
            return ForecastResult(
                symbol=sym,
                exchange=exch,
                generated_at=gen_at.isoformat(),
                horizon_days=horizon_days,
                model=cached["model"],
                mae=float(cached["mae"]) if cached["mae"] is not None else None,
                mape=float(cached["mape"]) if cached["mape"] is not None else None,
                forecast=points,
            )

    from app.services.market_data import get_bars

    bars = await get_bars(sym, exch, "1d", limit=500, pool=pool)
    if not bars:
        raise ValueError(f"No market data available for {sym} ({exch})")

    close_prices = [(b.timestamp, float(b.close)) for b in bars]

    forecast_json, model, mae, mape = await asyncio.to_thread(
        _compute_ensemble_sync, close_prices, horizon_days
    )

    await repo.upsert(
        symbol=sym,
        exchange=exch,
        horizon_days=horizon_days,
        model=model,
        mae=Decimal(str(round(mae, 4))) if mae is not None else None,
        mape=Decimal(str(round(mape, 4))) if mape is not None else None,
        forecast_json=forecast_json,
    )

    now = datetime.now(timezone.utc)
    points = [ForecastPoint(**p) for p in forecast_json]
    return ForecastResult(
        symbol=sym,
        exchange=exch,
        generated_at=now.isoformat(),
        horizon_days=horizon_days,
        model=model,
        mae=mae,
        mape=mape,
        forecast=points,
    )
