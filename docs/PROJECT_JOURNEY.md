# AlphaSwarm: Complete Project Study Guide & Postmortem

This document serves as a complete study guide, historical record, and demonstration outline for the AlphaSwarm project. It chronicles the transition from an initial concept into a production-hardened, institutional-grade algorithmic trading terminal.

---

## 1. Project Inception & The Vision
AlphaSwarm was designed to bridge the gap between retail traders and quantitative developers. The core thesis was **BYOB (Bring Your Own Broker)**—a multi-tenant SaaS that never custodies user funds, thereby avoiding massive regulatory overhead.

**The Product Goals:**
- **Natural Language to Deployment:** Describe a strategy in plain English, and the AI (AutoGen) generates, validates, backtests, and deploys the Python code.
- **Zero-Bypass Risk Engine:** An unhackable risk layer that prevents any trade that violates tenant limits, capital limits, or market states.
- **Real-Time Web Terminal:** A Bloomberg-style, browser-based terminal with live charts, indicators, and P&L dashboards.

---

## 2. Phase-by-Phase Execution & Bug Fixes

### Phase 0-2: The Foundation
*What we built:* 
- A FastAPI backend backed by PostgreSQL 16 and Redis 7.
- A strict repository pattern (`BaseRepo`) to enforce `tenant_id` isolation at the database level.
- Multi-tenant JWT Authentication (RS256 with HS256 fallback for local dev).

*Challenges & Bug Fixes:* 
- We needed to connect Alembic to PostgreSQL without `psycopg2` (which requires heavy C-compilers). We fixed this by forcing Alembic to use the SQLAlchemy 2.0 async engine natively with `asyncpg`, keeping the Docker footprint incredibly slim and fast.

### Phase 3-4: The Execution & Risk Engine
*What we built:* 
- Integration with Alpaca (US Markets) and yfinance (Indian Markets).
- The `verify_order_intent()` risk engine, which gates every single broker API call.
- A Celery-based worker architecture (`StrategyRunAgent` and `ExecutionAgent`) for decoupled background trading.

*Challenges & Bug Fixes:* 
- **The Indian Market Data Issue:** We permanently banned `NSEpy` (due to severely broken scraping endpoints) and strictly migrated to `yfinance` with `.NS` / `.BO` suffixes for robust daily data.

### Phase 5: Strategy Builder & Backtesting
*What we built:* 
- A dual-path builder: No-Code (Natural Language via Microsoft AutoGen) and Quant (Monaco Editor).
- The Backtest Engine, which replays historical OHLCV bars through the *exact same* risk engine used in live trading.

*Challenges & Bug Fixes:* 
- **Backtest Metric Math:** We had to implement rigorous edge-case handling for financial metrics. We fixed `OverflowError` crashes on ultra-short CAGR calculations, correctly implemented Root-Mean-Square (RMS) for Sortino downside deviations, and used a `999.0` sentinel to reward (not penalize) strategies with zero max drawdown.

### Phase 6: Frontend Terminal & WebSockets
*What we built:* 
- A Next.js 14 App Router frontend with TradingView Lightweight Charts v4.
- Real-time P&L Dashboard, Equity Curves, and a top-bar Notification bell.
- A WebSocket fan-out system broadcasting Redis Pub/Sub events directly to the browser.
- Rule-based AI Analysis (EMA/RSI trend synthesis) and Terminal performance tabs.

*Challenges & Bug Fixes:* 
- **WebSocket Race Conditions:** The React HTTP payload resolution was accidentally overwriting live WS data. We fixed the state to properly merge.
- **ASGI Blocking:** Synchronous Redis `.publish()` calls inside async FastAPI routes were blocking the entire ASGI event loop. We swapped entirely to `aioredis` for unblocked performance.

### Phase 7: Production Hardening & Security (The Deep Audit)
This phase was characterized by a massive security and concurrency overhaul to prepare for seed-funding and live capital execution.

*Critical Challenge 1: The TOCTOU Concurrency Bug*
- **The Bug:** Workers checking the daily notional cap or max open positions could double-fill if signals arrived at the exact same millisecond.
- **The Fix:** We implemented `pg_advisory_xact_lock` using a 64-bit integer lock (MD5 hash) to prevent collisions. Crucially, we moved the DB `positions` query *inside* the transaction block so workers always read the most up-to-date position counts.

*Critical Challenge 2: The Sandbox Escape*
- **The Bug:** Users writing Python code in the browser could bypass the RestrictedPython sandbox using string subclassing (`class S(str): def startswith...`), `iter(int, 1)` CPU DoS attacks, and string `.format()` memory leaks.
- **The Fix:** We heavily locked down `_guarded_getattr`, enforced `type(name) is str`, blocked format maps, and modified `_write_guard` to raise exceptions instead of allowing state mutation. We also replaced Pandas DataFrames with a heavily sanitized `ReadOnlyDataFrame`.

*Critical Challenge 3: Phantom Failures & Connection Leaks*
- **The Bug:** Long-running strategies were being prematurely marked as `failed` by the Celery Beat heartbeat checker, and the system was leaking Redis sockets by creating a new `ConnectionPool` on every log.
- **The Fix:** We implemented a globally cached Redis pool. We also injected a `run_repo.touch()` heartbeat ping directly inside the `tasks.py` execution loop so the database knows the worker is still actively processing a symbol.

---

## 3. The Architecture Stack
- **Frontend:** Next.js 14, TailwindCSS, TradingView Lightweight Charts v4.
- **Backend:** FastAPI, Python 3.11, asyncpg (No ORM for maximum speed).
- **Workers:** Celery, Redis.
- **AI Integration:** Microsoft AutoGen, Claude Sonnet 4.6.
- **Data/Math:** pandas-ta (for indicators), Prophet, ARIMA.
- **Security:** HKDF Fernet Key Envelope Encryption, RestrictedPython, `slowapi` Rate Limiting.

---

### Phase 8: The Retail Wealth-Tech Pivot & Multi-Market Operations
*What we built:* 
- Full pivot from an active "Quant Terminal" to a retail-friendly "Goal-Based Investment Advisor".
- Replaced the scary AI bot generation empty states with a Goal-Based Wizard (Retirement, Education).
- Implemented **XIRR (Extended Internal Rate of Return)** metrics and Asset Allocation Donut Charts instead of Absolute P&L.
- Built `MarketClock` for intelligent 24/7 market state handling (NASDAQ vs NSE/BSE) where backtesting/agent deployment remains 24/7 unlocked, but live execution is cleanly gated.
- Built the `OAuthManager` with a `retry_on_401` wrapper for Upstox, Zerodha, and AngelOne to seamlessly refresh daily expiring Indian broker tokens transparently.

*Challenges & Bug Fixes:* 
- **Database Schema Flaws:** Initial models lacked `tenant_id` on user mandates, and left `ON DELETE SET NULL` constraints that could secretly orphan active SIPs. We patched the architecture with strict `CHECK` constraints on status, non-negative `rollover_cash`, and properly normalized OAuth fields.

### Phase 9: Institutional-Grade Backtesting Upgrades (HRT / JS Standard)
*What we built & fixed:* 
- Elevated the backtester math to compete with proprietary quant firms like Jane Street and HRT.
- **Volume Participation Cap:** Enforced a strict 10% max participation rate to simulate real-world slippage and market impact (per Almgren-Chriss), dropping unfillable remainder volume.
- **Gap & Slippage Reality:** Fixed a hallucination where gapped stop-losses magically filled at the stop price rather than the adverse opening gap price.
- **Precision Truncation:** Removed forced `round(val, 2)` truncation for Alpaca bracket legs, preserving 4-decimal precision for penny stocks.
- **Cost Math:** Made the profit factor and win-rate commission-aware, added short-side borrow cost financing penalties, and accounted for terminal liquidation commissions.
- **Risk Guardrails:** Hard-wired the simulation to properly pass `current_position_value` to `verify_order_intent` so it couldn't bypass the max open position limits during backtesting.

---

## 4. What is to be done? (Phase 10 & Beyond)
While the core system is heavily fortified, the following represents the immediate scaling roadmap:

1. **Tax-Loss Harvesting Engine:** Implement FIFO accounting and automated harvesting algorithms to optimize around the Indian ₹1.25L LTCG tax exemption.
2. **Account Aggregator (AA) Integration:** Fetch external mutual fund and stock portfolios via the RBI AA framework for holistic AI advisory.
3. **Billing & Subscriptions:** Integrate Stripe/Razorpay to unlock the Pro and Quant tiers for users.
4. **Social Trading:** Allow users to publish their equity curves and strategy configurations to a public marketplace for copy-trading.

---

### End of Document
*Use this artifact to prepare for architecture reviews, seed funding pitches, and onboarding new quantitative engineers.*
