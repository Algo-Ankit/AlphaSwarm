# AlphaSwarm Engineering Handover

**Last Updated:** 2026-11-22
**Branch:** `main`
**Status:** Phases 0–12 MVP foundation, Track 1, AI Layer Upgrade, and Track 2 completed & hardened; ready for Track 3 post-MVP roadmap.

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

## 3. Critical Production Fixes (Track 1 — COMPLETED)

1. **Celery `beat_tasks` queue consumed & Beat service active:**
   - Added `beat_tasks` queue to Celery workers in `docker-compose.yml`, `docker-compose.prod.yml`, and `start_alphaswarm.bat`.
   - Added Celery Beat service container with persistent `beat_schedule` volume in Docker Compose.
2. **Upstox & OAuth reconciliation fixed (`app/worker/beat_tasks.py`):**
   - Decrypted and passed `access_token` to `get_executor` during `reconcile_positions`.
3. **Portfolio snapshots enriched (`app/worker/beat_tasks.py`):**
   - Computed `cash_balance` from broker accounts, `realized_pnl_today` from today's filled orders, and preserved broker equity.
4. **News sentiment client unified (`app/services/news_intel.py`):**
   - Removed uninstalled `anthropic` SDK; standardized on OpenAI/Gemini-compatible async client with neutral fallback.
5. **Replaced blocking `time.sleep(1)` with `await asyncio.sleep(1)` (`app/services/market_data.py`):**
   - Preserved non-blocking event loop across all market data retry loops.
6. **Orphaned `strategy_runs` prevented (`app/api/routes.py`):**
   - Moved validation and billing checks ahead of `run_repo.create()`.

---

## 4. AI Layer Upgrade (Google Gemini Default + NVIDIA NIM + BYOK — COMPLETED)

- **Platform Default:** Google Gemini (`gemini-2.5-flash` for ReAct strategy compilation and live bot execution; `gemini-2.5-pro` for deep investment advisory) via Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`), natively supported by `agent_framework.openai.OpenAIChatClient`.
- **Shared Platform Access:** Available out-of-the-box to all registered users via `.env` platform key with tenant rate-limiting.
- **Model Selector UI:** Frontend model picker in Strategy Builder (`frontend/src/app/strategies/new/page.tsx`), AI Settings (`frontend/src/app/settings/ai/page.tsx`), and Strategy details.
- **NVIDIA NIM & BYOK Presets:** Preset one-click configurations for NVIDIA NIM (`meta/llama-3.3-70b-instruct`), Groq, OpenRouter, and Ollama.

---

## 5. Core MVP Completion (Track 2 — COMPLETED)

- **Live Execution & Bot Lifecycle:**
  - Automated continuous execution: Celery Beat periodic scheduler task (`poll_and_execute_active_strategies` every minute on `beat_tasks`) with timeframe cadence & per-trading-day deduplication (`_should_run_for_timeframe` across `1m`/`5m`/`15m`/`30m`/`1h`/`4h`/`1d`/`1w`), `"regular"`/`"regular_only"` session matching, and `sip_paused` gating.
  - Approved rebalance execution: `POST /v1/notifications/{notif_id}/approve` (`app/api/notifications.py`) marks `approved_at` and immediately dispatches the strategy run to Celery (idempotently).
  - Paper vs. Live mode toggle in `frontend/src/app/strategies/[id]/page.tsx` persisted to `risk_config.paper_trading_only` via `PATCH /v1/strategies/{id}/risk` (fixed `Decimal` JSON serialization via `model_dump(mode="json")`).
  - Strategy lifecycle controls: `PATCH /v1/strategies/{id}/status` (active/paused), `PATCH /v1/strategies/{id}/risk` (risk limits), and `DELETE /v1/strategies/{id}`.
- **`/runs` Execution Visibility:**
  - Enabled `/runs` in `frontend/src/components/layout/Sidebar.tsx`.
  - Implemented `frontend/src/app/runs/page.tsx` with run stats, status/mode filters, and expandable order audit tables with exchange-aware currency formatting (`₹` for NSE/BSE, `$` for US/crypto).
  - Added backend endpoints: `GET /v1/runs` and `GET /v1/runs/{id}/orders`.
- **Complete Indian Broker Executors & Multi-Broker Routing:**
  - Added `brokers_for_exchange()` in `app/domain/broker_routing.py` across `app/worker/tasks.py` and copy-trading `fan_out_to_subscribers()` so NSE/BSE strategies route to whichever active Indian broker (`upstox`, `zerodha`, or `angelone`) the tenant connected.
  - Implemented `AngelOneExecutor` (SmartAPI) and `ZerodhaExecutor` (Kite Connect) in `app/services/execution.py` adhering to `BrokerExecutor` protocol with `.NS`/`.BO` suffix normalization, Angel One OpenAPI Scrip Master `symboltoken` resolution, and optional SmartAPI `api_key` support in `AngelOneLoginRequest` and `frontend/src/app/settings/brokers/page.tsx`.
- **Billing, Commons & Copy-Trading Polish:**
  - Normalized Swarm Tax billing (`app/worker/billing_tasks.py`) with `currency_for_exchange()` and `convert_amount()` so Stripe charges USD cents and Razorpay invoices INR paise accurately regardless of strategy exchange currency.
  - Added Unsubscribe / Stop Copying button on `frontend/src/app/leaderboard/page.tsx` calling `api.unsubscribeStrategy()`.
- **Real CAS & Broker Holdings Ingestion:**
  - Real statement upload on `frontend/src/app/portfolio/page.tsx` supporting NSDL/CDSL JSON and broker CSV exports (Zerodha, Upstox, Groww, Angel One) alongside sample data.
- **CI/CD & Split-Hosting (Vercel + Docker Compose):**
  - Added `frontend` lint, `npm run build`, and TypeScript CI job (Node 24) + safe git base-diff handling in `.github/workflows/main.yml`.
  - Added `frontend/vercel.json`, `"engines": { "node": "26.x" }` in `frontend/package.json`, and `deploy-vercel` job (`vercel@66.6.0` prebuilt deploy when `VERCEL_TOKEN`/`VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` secrets are set, or automatic Vercel Git integration). Linked `Algo-Ankit/AlphaSwarm` to Vercel project `alphaswarm` (`prj_jwOUbjex68jkcwwbGzwMZEnZFgOP`, `Root Directory = frontend`, `NEXT_PUBLIC_API_URL` pointing to the stateful Docker/Hetzner backend API hosting FastAPI + WebSockets + Celery + Postgres + Redis).

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
# Fast local test run with uv (verified 131/131 tests pass in ~5s)
& "$HOME\.local\bin\uv.exe" run pytest -q

# Run specific suite
& "$HOME\.local\bin\uv.exe" run pytest tests/test_risk.py -q
& "$HOME\.local\bin\uv.exe" run python tests/test_no_fund_custody.py

# Lint & Format
& "$HOME\.local\bin\uv.exe" run ruff check .
& "$HOME\.local\bin\uv.exe" run black --check .

# Frontend
cd frontend && npm install && npm run lint && npx tsc --noEmit && npm run build
```

---

## 8. Decision & Bugfix Audit Trail

| Date | Area | Fix / Decision | ADR | Key Files |
| :--- | :--- | :--- | :--- | :--- |
| 2026-11-22 | Queue / Beat | Consume `beat_tasks` queue + run Beat singleton service | [ADR-012](DECISIONS.md) | `docker-compose.yml`, `docker-compose.prod.yml`, `start_alphaswarm.bat` |
| 2026-11-22 | AI Layer | Gemini default + `model_override` + NVIDIA NIM + News client unification | [ADR-013](DECISIONS.md) | `app/services/strategy_compiler.py`, `app/services/news_intel.py`, `app/api/llm_configs.py` |
| 2026-11-22 | Async / Runs | Non-blocking `asyncio.sleep`; pre-validate billing/risk before `run_repo.create()` | [ADR-014](DECISIONS.md) | `app/services/market_data.py`, `app/api/routes.py` |
| 2026-11-22 | Scheduler & Risk | `_should_run_for_timeframe` daily dedup, `sip_paused` check, `Decimal` JSON fix, Live/Paper UI toggle, rebalance approval dispatch | [ADR-014](DECISIONS.md) | `app/worker/beat_tasks.py`, `app/api/routes.py`, `app/api/notifications.py`, `frontend/src/app/strategies/[id]/page.tsx` |
| 2026-11-22 | Indian Brokers | Upstox token reconciliation, multi-broker NSE/BSE routing, `.NS`/`.BO` strip, Angel One `symboltoken` + SmartAPI key | [ADR-015](DECISIONS.md) | `app/domain/broker_routing.py`, `app/services/execution.py`, `app/worker/tasks.py`, `app/api/brokers.py` |
| 2026-11-22 | Billing & UI | Swarm Tax USD/INR FX conversion (`convert_amount`); `₹`/`$` currency display in `/runs` | [ADR-009](DECISIONS.md) | `app/worker/billing_tasks.py`, `frontend/src/app/runs/page.tsx` |
| 2026-11-22 | CI/CD & Docs | Frontend CI (`lint`/`build`/`tsc`, Node 24/26.x), `frontend/Dockerfile` (`node:24-alpine`), `frontend/vercel.json`, `deploy-vercel` CD job, Vercel Git link (`prj_jwOUbjex68jkcwwbGzwMZEnZFgOP`), Niyam 3-file doc parity | [ADR-012](DECISIONS.md), [ADR-016](DECISIONS.md) | `.github/workflows/main.yml`, `.github/workflows/deploy.yml`, `frontend/Dockerfile`, `frontend/package.json`, `frontend/vercel.json`, `CLAUDE.md`, `AGENTS.md`, `docs/DECISIONS.md`, `docs/HANDOVER.md` |
