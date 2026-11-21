# AlphaSwarm Engineering Handover

**Last Updated:** 2026-11-21
**Branch:** `main`
**Status:** Phases 0–12 MVP foundation built; entering bugfix, AI default/model-picker upgrade, and full-product completion sprint.

---

## 1. Repository & Stack Snapshot

- **Backend Control Plane (`app/`):** FastAPI + `asyncpg` (raw SQL, no ORM) + Alembic (`0001` → `0014`) + `slowapi` rate limiting + Sentry SDK.
- **Execution & Beat Workers (`app/worker/`):** Celery 5 + Redis 7 (`trading_tasks` and `beat_tasks` queues).
- **AI Orchestration:** Microsoft Agent Framework (`agent-framework-core`, `agent-framework-openai`), `RestrictedPython` sandbox (`ReadOnlyDataFrame`, AST prescan, execution timeouts).
- **Market Data & Analytics:** Alpaca Data API (US/crypto) + `yfinance` (India `.NS`/`.BO` & global EOD), `pandas-ta`, Prophet + ARIMA ensemble, GBM Monte Carlo, NewsAPI + Alpha Vantage.
- **Frontend (`frontend/`):** Next.js 14 App Router, React 18, TailwindCSS, TradingView Lightweight Charts v4, Chart.js, Monaco Editor.
- **Tests & CI/CD:** 15 pytest suites in `tests/`; GitHub Actions in `.github/workflows/main.yml` (CI) and `.github/workflows/deploy.yml` (GHCR image build/push).

---

## 2. Implemented Subsystems

- **Auth & Identity (`app/api/auth.py`, `app/services/auth.py`, `app/services/oauth_manager.py`):**
  - Email + password (RS256/HS256 JWT + rotating refresh tokens with reuse detection), email verification, password reset.
  - Passwordless Email/Phone OTP login (`app/services/sms.py`, `app/services/email.py`).
  - Google OAuth identity login and "Continue with Upstox" broker-identity login.
- **BYOB & Crypto (`app/api/brokers.py`, `app/services/broker_crypto.py`):**
  - HKDF + Fernet v2 per-record salted encryption for broker keys/tokens.
  - Alpaca API-key connection + live test; Upstox OAuth, Zerodha OAuth, Angel One TOTP login flows.
- **Market Data, Terminal & Forecasting (`app/api/market.py`, `app/api/ws.py`, `frontend/src/app/terminal/`):**
  - Canonical `Bar` model, Postgres `market_data_cache`, server-side `pandas-ta` indicators, symbol search.
  - Live WebSocket fan-out (`/v1/ws/bars/{symbol}`, `/v1/ws/portfolio`, `/v1/ws/run/{run_id}`).
  - Terminal chart with overlays (EMA 20/50/200, SMA 50, BB 20-2, VWAP), log scale, RSI & MACD panes, Forecast, News, Performance, and AI Analysis tabs.
- **Risk Engine & Execution (`app/domain/risk.py`, `app/services/execution.py`, `app/worker/tasks.py`):**
  - Non-bypassable `verify_order_intent()` enforcing market hours, allowed symbols, per-order cap, daily notional cap (FX-aware via `broker_routing.py`), open position limits, and paper-trading gate.
  - 64-bit PostgreSQL transactional advisory locks (`pg_advisory_xact_lock`) wrapping read → check → place → persist.
  - Working `AlpacaExecutor` and `UpstoxExecutor`.
- **Strategy Builder, Sandbox & Backtester (`app/services/strategy_builder.py`, `strategy_sandbox.py`, `backtest.py`):**
  - ReAct Agent Framework writer + explainer + `validate_strategy_code` tool.
  - Hardened `RestrictedPython` compiler + `ReadOnlyDataFrame`.
  - Bar-by-bar backtester with next-bar open fills, adverse gap fills, 10% volume participation cap, commissions, short-borrow costs, Sortino/Calmar/Sharpe/Profit Factor metrics.
- **Strategy Commons, Social Feed & AI Advisor (`app/api/social.py`, `social_feed.py`, `ai_advisor.py`):**
  - Immutable published strategy snapshots (`≥3` backtests gate), fork lineage graph, out-of-sample (OOS) scorecard recomputation, proportional copy-trade fan-out, Swarm feed + likes.
  - AI Advisor grounded in published commons strategies; deterministic + AI holdings risk review (`/v1/portfolio/risk-review`).
- **Billing & Wealth (`app/api/billing.py`, `app/api/portfolio.py`, `app/worker/billing_tasks.py`):**
  - Dual-gateway Quant Tier checkout + signature-verified webhooks (Stripe USD + Razorpay INR).
  - Unified holdings (`upload-cas` / `unified`), Monte Carlo GBM projection, Goal Wizard, XIRR, SIP pause/lump-sum endpoints.

---

## 3. Active Debug Backlog (Track 1 — Fix First)

1. **Celery `beat_tasks` queue unconsumed & missing Beat service in Compose:**
   - `docker-compose.prod.yml` runs `worker` with `-Q trading_tasks` only — `beat_tasks` (`snapshot_portfolio`, `reconcile_positions`, `check_worker_heartbeats`, `recompute_commons_oos`, `charge_swarm_tax`, news/forecast refresh) never run.
   - `docker-compose.yml` lacks a `beat` service and `-Q trading_tasks,beat_tasks`.
   - `start_alphaswarm.bat` also passes `-Q trading_tasks` only.
2. **Upstox reconciliation crashes (`app/worker/beat_tasks.py`):**
   - `reconcile_positions` calls `get_executor(broker, api_key=..., secret_key=..., paper=...)` without `access_token`, failing for OAuth brokers like Upstox (and crashing if `key_encrypted`/`secret_encrypted` is absent).
3. **Portfolio snapshots ignore broker equity & today's realized P&L (`app/worker/beat_tasks.py`):**
   - `snapshot_portfolio` hardcodes `cash_balance = NULL`, sets `total_equity = open_pnl + realized_today`, and sums all-time `positions.realized_pnl` instead of today's realized P&L / broker equity.
4. **News sentiment imports uninstalled `anthropic` (`app/services/news_intel.py`):**
   - `_classify_batch` imports `anthropic`, which is not in `requirements.txt`, instead of using the OpenAI-compatible client / Gemini default / BYOK pattern used elsewhere.
5. **Blocking `time.sleep(1)` inside async loops (`app/services/market_data.py`):**
   - `_fetch_alpaca` and `_fetch_yfinance` call blocking `time.sleep(1)` inside `async def` retry loops instead of `await asyncio.sleep(1)`.
6. **Orphaned `strategy_runs` rows on validation/billing rejection (`app/api/routes.py`):**
   - `run_strategy` inserts a `strategy_runs` row before checking `paper_trading_only` (400) and active Quant Tier subscription (402), leaving stuck `queued` rows.

---

## 4. Planned AI Upgrade (Gemini Default + Model Picker + BYOK)

- **Platform Default:** Google Gemini (`gemini-2.5-flash` for ReAct strategy compilation and agent execution; `gemini-2.5-pro` for deep investment advisory) via Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`), natively supported by `agent_framework.openai.OpenAIChatClient`.
- **Shared Platform Access:** Available out-of-the-box to all registered users via `.env` platform key with tenant rate-limiting, removing the founder-only barrier while keeping the product zero-friction.
- **Model Selector UI:** Frontend dropdown across Strategy Builder, AI Advisor, and Settings to select Gemini models or custom endpoints.
- **Full BYOK / BYOB Flexibility:** Retain full BYOK support in Settings where any user can bring their own API key and custom `base_url` (NVIDIA NIM / Nemotron, Groq, OpenRouter, local Ollama) for unthrottled runs.

---

## 5. Core MVP Completion Backlog (Track 2)

- **Live Execution & Bot Lifecycle:**
  - Automated continuous execution: Celery Beat periodic scheduler task (`poll_and_execute_active_strategies`) executing active live/paper strategies on their bar timeframe (1m/5m/15m/daily) during market hours.
  - Add Paper vs. Live mode toggle in `frontend/src/app/strategies/[id]/page.tsx` (currently hardcodes `dryRun = true`).
  - Add strategy stop/pause, delete, and risk-config edit endpoints & UI.
- **`/runs` & Execution Visibility:**
  - Enable `/runs` in `frontend/src/components/layout/Sidebar.tsx` (currently `"Soon"`) and add REST endpoints + UI for run history, orders log, and open positions.
- **Complete Indian Broker Execution (`Zerodha` & `Angel One`):**
  - Implement `AngelOneExecutor` (SmartAPI, 100% free API) and `ZerodhaExecutor` in `app/services/execution.py`.
  - Complete Upstox and Alpaca executor hardening.
  - Support user-preferred/connected broker routing in `app/domain/broker_routing.py` and live connection checks in `app/api/brokers.py` (`test_broker`).
- **SIP & Rebalance Automation:**
  - Wire Celery Beat tasks to execute scheduled SIP contributions (respecting `sip_paused`) and approved `rebalance_approval` notifications (`approved_at IS NOT NULL`).
- **Commons, Copy-Trading & Billing Polish:**
  - Add Unsubscribe / Stop Copying button on `frontend/src/app/leaderboard/page.tsx` (backend `DELETE /v1/social/subscribe/{id}` exists).
  - Complete Razorpay Swarm Tax USD→INR FX conversion + `payment.captured` webhook handling in `app/api/billing.py` to credit `creator_balances`.
  - Add Creator Earnings view and Subscription Cancel/Manage UI.
- **Real CAS & Broker Holdings Ingestion:**
  - Add CSV/JSON/PDF CAS upload, manual holding CRUD, and live broker holdings sync in `frontend/src/app/portfolio/page.tsx` (replacing sample-only button).

---

## 6. Post-MVP Roadmap (Track 3)

- **Tax-Loss Harvesting Engine:** FIFO lot accounting + automated harvesting around India's ₹1.25L LTCG exemption.
- **Account Aggregator (RBI AA):** Consented pull of external mutual fund/equity holdings.
- **Corporate-Actions Pipeline:** Auto-adjust bars, positions, and backtests for splits, bonuses, dividends, and mergers.
- **e-NACH / UPI AutoPay Mandates:** Fully automated recurring SIP funding.
- **Centralized Intraday Feed Handler (TimescaleDB + Broker WS):** Multiplex live ticks across tenants.
- **SEBI Peak-Margin & Circuit-Limit Awareness:** Cleared-vs-uncleared cash and pre-open session rules.

---

## 7. Local Dev & Verification Commands

```bash
# Fast local test run with uv (verified 121/121 tests pass in ~10s)
& "$HOME\.local\bin\uv.exe" run pytest -q

# Run specific suite
& "$HOME\.local\bin\uv.exe" run pytest tests/test_risk.py -q
& "$HOME\.local\bin\uv.exe" run python tests/test_no_fund_custody.py

# Lint & Format
& "$HOME\.local\bin\uv.exe" run ruff check .
& "$HOME\.local\bin\uv.exe" run black --check .

# Frontend
cd frontend && npm install && npm run lint && npm run build
```
