"""
Monte Carlo wealth simulator — projects how a portfolio grows when a strategy's
return profile is applied on top of a monthly SIP, using Geometric Brownian
Motion (GBM).

Each of N simulations is an independent random walk of monthly log-returns drawn
from the strategy's expected CAGR (drift) and annual volatility (diffusion). The
SIP contribution is added at the end of every month. We then take the 10th / 50th
/ 90th percentile of the simulated wealth at each year horizon — pessimistic,
median and optimistic outcomes.

Pure-numpy and CPU-light (≤ 240 monthly steps × N sims, fully vectorised across
sims), so it runs inline without a thread pool.
"""

from dataclasses import dataclass

import numpy as np

# Guardrails — keep the simulation bounded and the request cheap.
_MIN_SIMS = 1000
_MAX_SIMS = 50_000
_MAX_YEARS = 40
_MONTHS_PER_YEAR = 12


@dataclass
class YearProjection:
    year: int
    contributed: float  # cumulative capital invested by end of this year
    pessimistic: float  # 10th percentile wealth
    median: float  # 50th percentile wealth
    optimistic: float  # 90th percentile wealth

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "contributed": round(self.contributed, 2),
            "pessimistic": round(self.pessimistic, 2),
            "median": round(self.median, 2),
            "optimistic": round(self.optimistic, 2),
        }


@dataclass
class MonteCarloResult:
    current_portfolio_value: float
    monthly_contribution: float
    expected_cagr: float  # annual, as a fraction (0.12 == 12%)
    annual_volatility: float  # annual, as a fraction
    years: int
    simulations: int
    total_contributed: float
    projections: list[YearProjection]
    disclaimer: str = (
        "Monte Carlo projection of a stochastic model — not a guarantee of future "
        "returns. Past performance does not predict future results."
    )

    def to_dict(self) -> dict:
        return {
            "current_portfolio_value": self.current_portfolio_value,
            "monthly_contribution": self.monthly_contribution,
            "expected_cagr": self.expected_cagr,
            "annual_volatility": self.annual_volatility,
            "years": self.years,
            "simulations": self.simulations,
            "total_contributed": round(self.total_contributed, 2),
            "projections": [p.to_dict() for p in self.projections],
            "disclaimer": self.disclaimer,
        }


def run_monte_carlo(
    *,
    current_portfolio_value: float,
    monthly_contribution: float,
    expected_cagr: float,
    annual_volatility: float,
    years_to_forecast: int,
    simulations: int = _MIN_SIMS,
    seed: int | None = None,
) -> MonteCarloResult:
    """
    Project future wealth via GBM. ``expected_cagr`` and ``annual_volatility`` are
    fractions (0.12 == 12%). Returns P10/P50/P90 wealth at each year.

    Raises ValueError on invalid inputs.
    """
    if current_portfolio_value < 0:
        raise ValueError("current_portfolio_value must be non-negative")
    if monthly_contribution < 0:
        raise ValueError("monthly_contribution must be non-negative")
    if annual_volatility < 0:
        raise ValueError("annual_volatility must be non-negative")
    years = int(years_to_forecast)
    if years < 1 or years > _MAX_YEARS:
        raise ValueError(f"years_to_forecast must be between 1 and {_MAX_YEARS}")
    if current_portfolio_value == 0 and monthly_contribution == 0:
        raise ValueError("Either a starting value or a monthly contribution is required")

    n_sims = max(_MIN_SIMS, min(int(simulations), _MAX_SIMS))
    months = years * _MONTHS_PER_YEAR
    dt = 1.0 / _MONTHS_PER_YEAR

    mu = float(expected_cagr)
    sigma = float(annual_volatility)
    # GBM discretised to monthly steps: the drift term is corrected by -½σ² so the
    # *expected* annual growth of the median path matches the requested CAGR.
    drift = (mu - 0.5 * sigma * sigma) * dt
    diffusion = sigma * np.sqrt(dt)

    rng = np.random.default_rng(seed)
    values = np.full(n_sims, float(current_portfolio_value), dtype=np.float64)

    projections: list[YearProjection] = [
        YearProjection(
            year=0,
            contributed=float(current_portfolio_value),
            pessimistic=float(current_portfolio_value),
            median=float(current_portfolio_value),
            optimistic=float(current_portfolio_value),
        )
    ]

    for month in range(1, months + 1):
        z = rng.standard_normal(n_sims)
        values *= np.exp(drift + diffusion * z)
        # SIP contributed at month-end (no growth applied in the month it lands).
        values += monthly_contribution
        # Numerical floor — GBM is multiplicative and can't go negative.
        np.maximum(values, 0.0, out=values)

        if month % _MONTHS_PER_YEAR == 0:
            year = month // _MONTHS_PER_YEAR
            p10, p50, p90 = np.percentile(values, [10, 50, 90])
            contributed = current_portfolio_value + monthly_contribution * month
            projections.append(
                YearProjection(
                    year=year,
                    contributed=float(contributed),
                    pessimistic=float(p10),
                    median=float(p50),
                    optimistic=float(p90),
                )
            )

    total_contributed = current_portfolio_value + monthly_contribution * months
    return MonteCarloResult(
        current_portfolio_value=float(current_portfolio_value),
        monthly_contribution=float(monthly_contribution),
        expected_cagr=mu,
        annual_volatility=sigma,
        years=years,
        simulations=n_sims,
        total_contributed=float(total_contributed),
        projections=projections,
    )
