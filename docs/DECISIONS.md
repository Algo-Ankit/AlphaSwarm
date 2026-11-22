# AlphaSwarm Architecture Decision Records (ADRs)

Concise log of the binding engineering decisions and trade-offs across the platform.

---

## ADR-001: Microsoft Agent Framework over LangChain and AutoGen
- **Decision:** Use `agent-framework-core` + `agent-framework-openai` exclusively for all LLM agent workflows (`strategy_builder.py`, `ai_advisor.py`).
- **Context:** LangChain ships frequent breaking minor updates unacceptable for financial execution pipelines, and Microsoft AutoGen moved into maintenance mode following Agent Framework 1.0 GA.
- **Consequences:** All LLM providers integrate through `OpenAIChatClient` (`base_url`, `api_key`, `model`) with native tool calling (ReAct `validate_strategy_code` loop). LangChain and `autogen-*` packages are permanently banned.

## ADR-002: Platform-Default Gemini Models + Model Picker + Full BYOK Override
- **Decision:** Provide Google Gemini models as the default platform choice with an explicit model picker across AI features, while keeping full Bring Your Own Key (BYOK) override for any OpenAI-compatible provider (Groq, OpenRouter, NVIDIA NIM, Ollama, etc.).
- **Context:** Strict BYOK-only creates onboarding friction for first-time users, while hardcoding a single model blocks power users who want specialized or stronger reasoning/open-source models.
- **Consequences:** Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) works seamlessly with `OpenAIChatClient`, requiring no provider-specific SDK fragmentation (including unifying news sentiment away from `anthropic`).

## ADR-003: Bring Your Own Broker (BYOB) — Zero Fund Custody
- **Decision:** Never custody user capital, accept deposits, manage wallets, or process withdrawals/escrow. Execute orders directly against each user's own regulated broker account (Alpaca, Upstox, Zerodha, Angel One).
- **Context:** Pooling or holding client funds triggers money-transmission / brokerage / SEBI RIA-PMS custody licensing overhead.
- **Consequences:** `tests/test_no_fund_custody.py` enforces this invariant across `app/` in CI. Copy-trading fans out proportional signals into each subscriber's own broker account.

## ADR-004: Zero-Bypass Risk Engine (`verify_order_intent`) & Transactional Advisory Locks
- **Decision:** Every order intent — live, paper, backtest, or copy-trade — must pass `verify_order_intent()` in `app/domain/risk.py`. Live/paper worker execution wraps position read → daily notional read → risk check → broker placement → DB write inside a single transaction guarded by a 64-bit `pg_advisory_xact_lock`.
- **Context:** Checking risk limits outside the transaction caused TOCTOU double-fills under concurrent signals; separate code paths in backtests caused silent parity drift.
- **Consequences:** Guaranteed single-door risk enforcement, FX-normalized platform notional caps (`app/domain/broker_routing.py`), and atomic per-strategy/per-subscriber serialization.

## ADR-005: Raw `asyncpg` with Enforced `tenant_id` Isolation via `BaseRepo`
- **Decision:** Use raw SQL over `asyncpg` pools and enforce multi-tenant scoping in `app/db/base_repo.py` instead of an ORM.
- **Context:** Read-heavy terminal/chart/order workloads require low overhead and strict non-blocking async I/O; ORMs add latency and mask query plans.
- **Consequences:** No sync DB drivers in FastAPI routes; every tenant-scoped query filters by `tenant_id`. Alembic runs async migrations using SQLAlchemy's asyncpg dialect without `psycopg2`.

## ADR-006: `pandas-ta` over TA-Lib; Alpaca / `yfinance` over Banned `NSEpy`
- **Decision:** Compute all technical indicators server-side via `pandas-ta`; normalize all OHLCV data to the canonical `Bar` model from Alpaca Data API (US/crypto) and `yfinance` (Indian `.NS`/`.BO` & global EOD).
- **Context:** TA-Lib fails C compilation on many developer/CI environments; `NSEpy` relies on broken NSE scraping endpoints.
- **Consequences:** Pure-Python installs across Windows/Linux/Docker and one canonical `Bar` schema across charts, indicators, backtests, and live workers.

## ADR-007: Hardened `RestrictedPython` Sandbox + `ReadOnlyDataFrame` + Timeout
- **Decision:** Compile and run user- and AI-generated strategies inside `RestrictedPython` with AST prescanning, str-subclass guards, format-string denylists, `ReadOnlyDataFrame` isolation, and execution timeouts (`exec_timeout.py`).
- **Context:** Accepting arbitrary Python strategies from a browser editor or LLM opens RCE and CPU DoS vectors if raw `pandas.DataFrame` or unrestricted builtins leak into scope.
- **Consequences:** Strategies operate strictly via `BaseStrategy.on_bar()`, `self.indicators`, `self.close`, and safe `math`/`datetime` utilities.

## ADR-008: Institutional Backtest Realism
- **Decision:** Simulate fills at the next bar's open with adverse gap fills on stops, a 10% volume-participation cap (Almgren–Chriss market impact), bid/ask spread, commissions, short-borrow financing, terminal liquidation cost, and timeframe-aware annualization.
- **Context:** Retail backtesters overstate Sharpe and return by assuming infinite liquidity and exact stop fills.
- **Consequences:** Backtest outputs reflect realistic friction and share the exact `verify_order_intent()` risk checks used in production.

## ADR-009: Dual-Gateway Billing (Stripe USD + Razorpay INR/UPI) & Swarm Tax
- **Decision:** Route USD subscriptions to Stripe Checkout and INR subscriptions (UPI AutoPay / e-mandate) to Razorpay Subscriptions, converging on `tenants.subscription_status` to gate live agent deployment. Bill copy-trade subscriptions a monthly 1% Swarm Tax split 50/50 between platform and creator.
- **Context:** Stripe faces RBI recurring-mandate restrictions in India, requiring native UPI AutoPay support via Razorpay.
- **Consequences:** Webhook handlers must verify signatures before state updates, and creator ledger credits only occur after confirmed payment collection (never on unpaid invoices).
- **Design & Bugfixes Log:**
  - *Swarm Tax FX Normalization (2026-11-22):* Fixed `app/worker/billing_tasks.py` (`_charge_swarm_tax_async`, `_attempt_charge`) where Razorpay orders were created with raw `round(amount_usd * 100)` without currency conversion. Joined `strategies.exchange` via `public_strategies`, derived native currency via `currency_for_exchange()`, and converted to USD cents (Stripe) or INR paise (Razorpay) via `broker_routing.convert_amount()`, recording `creator_balances.currency` accurately.

## ADR-010: Immutable Strategy Commons Versions, Fork Lineage & OOS Scorecards
- **Decision:** Require `>= 3` on-platform backtests to publish; freeze each published listing to an immutable `strategy_versions` row; track fork lineage graphs; and run daily out-of-sample (OOS) backtests on post-publish data.
- **Context:** Editable posts break copy/fork trust, and in-sample-only leaderboards degenerate into survivorship-biased overfitting galleries.
- **Consequences:** Alpha decay after publication is measured and shown transparently alongside in-sample metrics.

## ADR-011: TradingView Lightweight Charts v4 (Terminal) & Chart.js (Wealth)
- **Decision:** Use TradingView `lightweight-charts` v4 exclusively for candlestick/OHLCV/equity-overlay terminal charts and `chart.js` for Monte Carlo wealth fan charts and allocation donuts.
- **Context:** General charting libraries cannot maintain terminal responsiveness across thousands of candles and synchronized sub-panes.
- **Consequences:** Client chart wrappers mount via `useRef`, compute TA overlays consistently with backend specs, and merge auto-reconnecting WebSocket ticks with REST history.

## ADR-012: Bootstrap Production Topology (Hetzner + Cloudflare + Vercel + GHCR)
- **Decision:** Run FastAPI, Celery workers, Celery Beat, PostgreSQL 16, Redis 7, and Nginx in Docker Compose on a single/scaled VPS (Hetzner), fronted by Cloudflare, with Next.js on Vercel and images published to GHCR via GitHub Actions.
- **Context:** Keeps monthly infrastructure near ~€15/mo while preserving horizontal API/worker scaling and automated container delivery. Backend cannot live solely on Vercel because FastAPI WebSockets (`/v1/ws/*`) and 1-minute Celery Beat/worker queues with Postgres advisory locks require persistent stateful processes.
- **Consequences:** All stateful services use explicit healthchecks, Celery Beat runs strictly as a singleton with persisted schedule volume, and production boot refuses default secrets.
- **Design & Bugfixes Log:**
  - *Track 1 Queue & Beat Wiring (2026-11-22):* Added `beat_tasks` to worker `-Q trading_tasks,beat_tasks` across `docker-compose.yml`, `docker-compose.prod.yml`, and `start_alphaswarm.bat`; added dedicated `beat` service with persisted `celerybeat_data` volume.
  - *Frontend CI & Vercel Readiness (2026-11-22):* Added `frontend` lint (`npm run lint`), production build (`npm run build`), and TypeScript (`npx tsc --noEmit`) checks + safe `git diff` base resolution in `.github/workflows/main.yml`; added `frontend/vercel.json` (Next.js framework + security headers) and optional `deploy-vercel` prebuilt CD job (`vercel@66.6.0`) in `.github/workflows/deploy.yml`.

## ADR-013: Google Gemini Default AI Platform Layer + Shared Access with Full BYOK/BYOB
- **Decision:** Default the platform AI provider to Google Gemini (`gemini-2.5-flash` for high-throughput ReAct strategy compilation and `gemini-2.5-pro` for deep investment advisory) via the standard OpenAI-compatible endpoint format (`https://generativelanguage.googleapis.com/v1beta/openai/`) natively supported by `OpenAIChatClient`. Provide shared platform Gemini access out-of-the-box for all users while preserving full BYOK (Bring Your Own Key) in user settings for custom endpoints (NVIDIA NIM, Groq, OpenRouter, Ollama) and higher rate limits.
- **Context:** Enables zero-barrier onboarding for new users to generate strategies and receive advisory immediately without requiring upfront API keys, while keeping the architecture 100% BYOK-capable.
- **Consequences:** Strategy compilation and advisory services fall back gracefully to the shared platform Gemini key for all users, with tenant-level rate limiting and audit logging.
- **Design & Bugfixes Log:**
  - *News Client Unification (2026-11-22):* Removed uninstalled `anthropic` SDK import in `app/services/news_intel.py`; standardized on OpenAI/Gemini-compatible async client with neutral sentiment fallback when unconfigured.
  - *Model Picker & NVIDIA NIM Presets (2026-11-22):* Added `model_override` to `StrategyCreateRequest`, `nvidia` provider in `app/api/llm_configs.py`, and presets in `frontend/src/app/settings/ai/page.tsx` and `frontend/src/app/strategies/new/page.tsx`.

## ADR-014: Celery Beat Periodic Strategy Polling & Market-Hours Automated Execution
- **Decision:** Automate live and paper bot execution via a Celery Beat periodic scheduler task (`poll_and_execute_active_strategies`) that polls all active, deployed strategies matching the current market session (NSE/BSE/US/Crypto) and timeframe, dispatching `execute_trading_strategy` Celery worker tasks with deduplicated run IDs.
- **Context:** Automated algorithmic trading requires scheduled bar execution without relying on browser sessions or constant manual intervention.
- **Consequences:** Celery Beat must have a dedicated container and schedule volume; runs are executed idempotently and recorded in `strategy_runs`.
- **Design & Bugfixes Log:**
  - *Timeframe Cadence, Daily Deduplication & SIP Pause (2026-11-22):* Fixed `poll_and_execute_active_strategies` where `1d`/`4h` strategies executed every minute; added `_should_run_for_timeframe()` enforcing exchange-local calendar day deduplication (`1d`), ISO week (`1w`), `4h`, `1h`, `30m`, `15m`, `5m`, and `1m`, plus matching both `"regular"` and `"regular_only"` `trade_session` values and skipping paused SIPs (`sip_paused=true`).
  - *Live/Paper Risk Config Persistence & Decimal Serialization (2026-11-22):* Fixed `PATCH /v1/strategies/{id}/risk` in `app/api/routes.py` to call `request.risk.model_dump(mode="json")` (preventing `Decimal` JSON crash) and preserve `currency`; wired Paper/Live toggle on `/strategies/[id]` to persist `paper_trading_only`.
  - *Orphaned Runs, Async Loop & Approved Rebalances (2026-11-22):* Moved validation/billing checks ahead of `run_repo.create()` in `app/api/routes.py`; replaced blocking `time.sleep(1)` in `app/services/market_data.py` with `await asyncio.sleep(1)`; wired `POST /v1/notifications/{notif_id}/approve` in `app/api/notifications.py` to dispatch approved lump-sum rebalance runs immediately; added exchange-aware `₹`/`$` formatting in `/runs`.

## ADR-015: Zero-Cost Indian Broker Stack: Upstox Hardening + Angel One SmartAPI + Zerodha Kite
- **Decision:** Fully harden Upstox & Alpaca executors, and implement Angel One SmartAPI (REST via `httpx`, 100% free retail trading API) and Zerodha Kite (REST via `httpx`) following the canonical `BrokerExecutor` protocol, strictly enforcing `verify_order_intent()` before any broker dispatch.
- **Context:** Aligns with the core mission to keep AlphaSwarm completely free for retail quants via Bring Your Own Broker (BYOB) and Bring Your Own Key (BYOK).
- **Consequences:** Zero fund custody, zero platform brokerage fees, unified `OrderIntent` / `OrderResult` model across all 4 brokers.
- **Design & Bugfixes Log:**
  - *Upstox Reconciliation & Snapshots (2026-11-22):* Decrypted and passed `access_token` in `reconcile_positions` and `snapshot_portfolio` (`app/worker/beat_tasks.py`); populated broker `cash_balance`, `equity`, and `realized_pnl_today`.
  - *Multi-Broker NSE/BSE Routing (2026-11-22):* Added `brokers_for_exchange()` in `app/domain/broker_routing.py` returning `("upstox", "zerodha", "angelone")` for NSE/BSE, replacing hardcoded single `"upstox"` lookup in `app/worker/tasks.py` and copy-trading `fan_out_to_subscribers()` (`app/services/execution.py`).
  - *Angel One Scrip Master Tokens, `.NS`/`.BO` Stripping & SmartAPI Key (2026-11-22):* Added `_strip_indian_suffix()` across Upstox/Zerodha/Angel One so `yfinance` tickers like `RELIANCE.NS` map cleanly to exchange instruments; added `_load_angelone_instruments()` resolving numeric `symboltoken` from Angel One's OpenAPI Scrip Master; added optional `api_key` in `AngelOneLoginRequest`, `oauth_manager.angelone_login()`, and Broker Settings UI.

## ADR-016: Multi-Agent Persistent Brain Governance (Niyam Protocol)
- **Decision:** Maintain three synchronized persistent brain documents as the single source of truth for all coding agents and human reviewers: `CLAUDE.md` + `AGENTS.md` (kept byte-identical), `docs/DECISIONS.md` (ADRs + Design & Bugfixes Logs), and `docs/HANDOVER.md` (live sprint status, verification commands, and audit trail).
- **Context:** Multiple AI models/agents (Claude, Gemini, Codex) work across threads on AlphaSwarm; drifting docs or undocumented bugfixes cause agents to repeat work, reintroduce bugs, or overlook design constraints.
- **Consequences:** Every task that changes architecture, fixes a bug, or completes a milestone MUST update `docs/DECISIONS.md`, `docs/HANDOVER.md`, and keep `CLAUDE.md`/`AGENTS.md` aligned before completion.

