# AlphaSwarm — Quantitative Methods & Signal Validity

This document explains the real mathematics behind every number the system produces.
No idealised curves. No marketing. Just the actual stochastic framework we operate in.

---

## 1. What Markets Actually Are

Price follows a **Geometric Brownian Motion (GBM)** baseline:

```
dS = μ·S·dt + σ·S·dW
```

Where `dW ~ N(0, dt)` is a Wiener process. In discrete log-return form:

```
r_t = ln(S_t / S_{t-1}) = (μ - σ²/2)·Δt + σ·√Δt·ε,   ε ~ N(0,1)
```

**The inconvenient truth:** Under pure GBM, `μ = 0` on a risk-adjusted basis — there
is no alpha to extract. Every strategy we run is a bet that the *real* data-generating
process has a mean term `μ > 0` (after costs) that is *not* fully priced.

GBM is a first-order approximation. Real markets exhibit:

| Stylised Fact | Implication for AlphaSwarm |
|---|---|
| Fat tails (kurtosis > 3) | Max drawdown happens faster than Gaussian models predict |
| Volatility clustering (GARCH effects) | ATR(14) is a lagging vol estimator — it underestimates risk in regime changes |
| Autocorrelation in squared returns | Momentum signals have real but transient predictive power |
| Microstructure noise at intraday freq | 1m signals are ~70% noise; 1d signals have a higher signal-to-noise ratio |

---

## 2. Probability That a Forecast Signal Is a True Alpha (Bayesian Framework)

The forecaster generates an ensemble signal. The question a quant asks is not
*"did the model predict up?"* but *"given the model predicted up, what is the
probability the move is real and not noise?"*

### Bayes' Theorem Applied to Trade Signals

Let:
- `H` = hypothesis: true directional move exists (genuine alpha)
- `E` = evidence: our ensemble model predicted this direction

```
P(H | E) = P(E | H) · P(H) / P(E)
```

Expanding the denominator:

```
P(H | E) = P(E|H) · P(H) / [P(E|H)·P(H) + P(E|¬H)·P(¬H)]
```

### Plugging In Real Numbers

Our ARIMA(1,1,0)+Prophet ensemble achieves roughly:
- **P(E | H)** ≈ 0.58 — sensitivity: when a true move exists, the model catches it 58% of the time
- **P(E | ¬H)** ≈ 0.42 — false positive rate: noise flagged as signal 42% of the time
- **P(H)** ≈ 0.52 — base rate: just over half of daily bars have a meaningful directional move (vs. pure noise)

```
P(H | E) = (0.58 × 0.52) / [(0.58 × 0.52) + (0.42 × 0.48)]
           = 0.3016 / (0.3016 + 0.2016)
           = 0.3016 / 0.5032
           ≈ 0.60
```

**The forecast signal is a true alpha ~60% of the time.** The remaining 40% is
noise that looks like signal. This is why:
1. We do not execute solely on forecast direction — the RSI/MACD confirmation layer
   is a second independent test, improving the joint precision.
2. We size positions using Kelly fraction (see §4), not fixed lot size.
3. Every signal goes through `verify_order_intent()` — if the risk engine rejects,
   we never execute, even on a "confident" forecast.

### MAPE to Confidence Interval

The system exposes `mape` (Mean Absolute Percentage Error) from backtest validation.
Map it to 1-sigma confidence on the forecast price:

```
σ_forecast = current_price × (MAPE / 100)
```

For MAPE = 2.1% on SPY at $500:
```
σ_forecast = 500 × 0.021 = $10.50
```

The Prophet 80% CI is approximately `±1.28σ` — for our example: `±$13.44`.
**If the 80% CI lower bound is still above current price, the signal confidence
is sufficient to size a position.**

---

## 3. Sharpe Ratio — What It Actually Measures

```
SR = (R̄ - R_f) / σ_R × √(bars_per_year)
```

Where `R̄` is the mean bar return, `σ_R` is the standard deviation of *all* bar
returns (same population — not just active-trade bars), and `√(bars_per_year)`
is the timeframe-correct annualization factor.

We use:
| Timeframe | bars_per_year | √(bpy) |
|---|---|---|
| 1d | 252 | 15.87 |
| 4h | 409.5 | 20.24 |
| 1h | 1638 | 40.47 |
| 5m | 19656 | 140.2 |
| 1m | 98280 | 313.5 |

### Why the Population Must Be Consistent

The bug this system previously had: computing `mean(all_returns) / std(active_returns_only)`.
This is mathematically undefined as a Sharpe ratio. A sparse strategy trading 5 times in 252 bars:
- `mean(all_returns)` ≈ 0 (mostly zeros dilute the mean)
- `std(active_returns)` inflated (only the 5 active days)
- Result: `Sharpe ≈ 0 / large_std ≈ 0` or `mean / near_zero_std → ±∞`

The correct formula uses `std(all_returns)`. A strategy holding cash has zero-return
bars — those *are* the strategy's risk profile and must be included.

### Sharpe in the Wild

A Sharpe of 1.0 annualised on daily data means you earn one standard deviation of
daily returns per year. Benchmarks:
- SR < 0.5: worse than a passive index on a risk-adjusted basis
- SR 0.5–1.0: acceptable for a systematic long-only strategy
- SR 1.0–2.0: institutional-grade; most quant funds operate here
- SR > 2.0: either exceptional or overfit — always check out-of-sample

**The system shows SR with 3 decimal places, but treat anything outside a
confidence interval as noise for backtests < 200 bars.**

---

## 4. Kelly Criterion — Optimal Position Sizing

The Kelly fraction maximises the long-run geometric growth rate:

```
f* = (p·b - q) / b
```

Where:
- `p` = probability of win (use backtest win rate / 100)
- `q` = 1 - p (probability of loss)
- `b` = average win / average loss (payoff ratio from backtest trades)

**Half-Kelly in practice:** Full Kelly maximises *geometric* growth but produces
drawdowns most humans cannot psychologically sustain. Most firms use `f*/2`.

```python
def kelly_fraction(win_rate_pct: float, avg_win: float, avg_loss: float) -> float:
    p = win_rate_pct / 100.0
    q = 1.0 - p
    b = avg_win / avg_loss if avg_loss > 0 else 0.0
    full_kelly = (p * b - q) / b if b > 0 else 0.0
    return max(0.0, full_kelly / 2.0)  # half-Kelly
```

The `max_order_notional` risk config is a hard cap, not a Kelly-derived size.
A future enhancement is to pass the backtest win_rate and payoff_ratio into
the risk config so the engine can size at half-Kelly subject to the notional cap.

---

## 5. Max Drawdown — Probability of Ruin

For GBM with drift `μ` and vol `σ`, the probability of hitting a drawdown level `D`
before recovering is:

```
P(ruin at level D) ≈ exp(-2μD / σ²)    [continuous approximation]
```

This is why the backtester halts at `equity ≤ 0` — once `μ < σ²/2` (the strategy
is net-destructive), the probability of eventual ruin approaches 1.

In practice:
- Max drawdown > 25% → probability of further drawdown is non-trivial; consider pausing
- Max drawdown > 50% → strategy requires +100% gain to break even; likely overfit

---

## 6. Forecast Alpha Decay

Even genuine alpha has a half-life. An AR(1) process has autocorrelation:

```
ρ(lag) = φ^lag
```

For our ARIMA(1,1,0) component, the AR coefficient `φ` is estimated from the data.
If `φ = 0.15` at daily resolution, the signal has a **half-life of:**

```
t_half = -ln(2) / ln(φ) = 0.693 / (-ln(0.15)) ≈ 0.37 days
```

This means the 1-day ARIMA forecast has essentially zero predictive power beyond
the next bar. **We do not chain ARIMA forecasts** — each day's forecast is
independent. The 5–10 day horizon uses Prophet (trend + seasonality decomposition),
not the AR component.

---

## 7. Slippage and Transaction Cost Reality

Every backtest run applies:

```
fill_price_buy  = next_open × (1 + slippage_bps / 10_000)
fill_price_sell = next_open × (1 - slippage_bps / 10_000)
```

Default `slippage_bps = 5` (0.05%). For liquid US large-caps (SPY, AAPL), real
market impact for orders < $10k is typically 1–3 bps. For small-caps or Indian
mid-caps, 10–30 bps is realistic.

A strategy that looks profitable at 0 bps slippage but breaks even at 10 bps
has no real edge — it is front-running the bid/ask spread in simulation.

Always run: `backtest @ 0bps`, `5bps`, `20bps`. If SR drops below 0.5 at 20bps,
the strategy has no robust edge.

---

## 8. The Information Coefficient (IC) Framework

The correlation between a forecast signal and the subsequent realised return is
the **Information Coefficient**:

```
IC = corr(forecast_direction, actual_return_next_bar)
```

Typical IC values in real markets:
- IC = 0.05: weak but statistically significant with 252+ observations
- IC = 0.10: solid signal — most institutional quant models operate here
- IC = 0.15+: either genuine edge or in-sample overfit — validate out-of-sample

**Fundamental Law of Active Management (Grinold):**

```
IR ≈ IC × √(breadth)
```

Where `breadth` = number of independent bets per year. A strategy with IC = 0.08
trading 1 symbol daily:

```
IR = 0.08 × √252 ≈ 1.27
```

The same IC applied to 10 uncorrelated symbols simultaneously:

```
IR = 0.08 × √(252 × 10) ≈ 4.01
```

This is why multi-symbol strategies (the `symbols` array in `StrategyCreateRequest`)
produce dramatically better risk-adjusted returns than single-symbol approaches —
*provided the signals are genuinely uncorrelated.*

---

*All statistics shown in the backtest panel are in-sample. Out-of-sample validation
(walk-forward, paper trading) is mandatory before live deployment.*
