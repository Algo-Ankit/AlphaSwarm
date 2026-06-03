<div align="center">

```
 █████╗ ██╗     ██████╗ ██╗  ██╗ █████╗ ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
██╔══██╗██║     ██╔══██╗██║  ██║██╔══██╗██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
███████║██║     ██████╔╝███████║███████║███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
██╔══██║██║     ██╔═══╝ ██╔══██║██╔══██║╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
██║  ██║███████╗██║     ██║  ██║██║  ██║███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
```

### **Bloomberg Terminal meets Linear. Built for the next generation of traders.**

*Describe a strategy in plain English. AI generates, validates, backtests, and deploys it.*  
*Monitor via a full trading terminal. No Bloomberg subscription required.*

---

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-FF6B35?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[![Build Status](https://img.shields.io/badge/Backend-Phase_2_Complete-success?style=flat-square)](https://github.com/Algo-Ankit/AlphaSwarm)
[![Phase](https://img.shields.io/badge/Current_Phase-3_(Market_Data)-blue?style=flat-square)](https://github.com/Algo-Ankit/AlphaSwarm)
[![Founding Members](https://img.shields.io/badge/Founding_Members-500_spots-gold?style=flat-square)](https://github.com/Algo-Ankit/AlphaSwarm)

</div>

---

## What is AlphaSwarm?

AlphaSwarm is a **production-grade, multi-tenant algorithmic trading SaaS** — a fundable startup MVP being built in public.

Two types of users are served simultaneously:

| User Type | Journey |
|-----------|---------|
| **Retail Trader (No-Code)** | Describe a strategy in plain English → AI generates + explains it → Backtest → Deploy paper → Go live |
| **Quant Developer** | Write Python in a browser Monaco editor → Sandbox validates → Backtest → Deploy |

The core thesis: **traders shouldn't need to build infrastructure**. AlphaSwarm handles the entire stack — data feeds, technical indicators, AI strategy generation, risk management, broker execution, and real-time monitoring — so traders can focus on edge, not engineering.

> **BYOB (Bring Your Own Broker)** — AlphaSwarm never touches your funds. All money lives in your own broker account (Alpaca, Upstox, Zerodha). AlphaSwarm sends orders via your API keys. This means: no money transmission license, no custody liability.

---

## Core Product Modules

<details>
<summary><strong>📊 Trading Terminal</strong> — The primary product screen</summary>

- **Candlestick chart** via [TradingView Lightweight Charts v4](https://tradingview.github.io/lightweight-charts/) — the only production-grade charting library
- **Timeframe selector**: 1m / 5m / 15m / 1h / 4h / 1D / 1W
- **Indicator overlays**: 20 EMA, 50 EMA, 200 EMA, Bollinger Bands, VWAP
- **Sub-charts**: RSI(14), MACD histogram + signal, Volume bars
- **Parameterizable**: `rsi(21)`, `macd(5,35,5)`, `bb(20,2.5)` — user-configurable at runtime
- All indicator values computed **server-side** via [pandas-ta](https://github.com/twopirllc/pandas-ta). Client displays only.

</details>

<details>
<summary><strong>🤖 AI Strategy Builder</strong> — Natural language → deployable Python</summary>

- User types: *"Buy RELIANCE when RSI(14) drops below 30 and close is above 200-day EMA. Sell when RSI crosses above 70."*
- `StrategyBuilderAgent` (Microsoft [AutoGen](https://github.com/microsoft/autogen) + Claude Sonnet 4.6) interprets → generates a validated `BaseStrategy` Python subclass
- Multi-turn conversation: generate → self-critique → fix
- User sees plain-English confirmation only; code hidden behind "Show Code" toggle
- Failure contract: always returns `{error, suggestion}` — never silently emits broken code

</details>

<details>
<summary><strong>📈 Backtesting Engine</strong> — Same risk checks as live trading</summary>

- `BacktestRunner` replays historical OHLCV bars through `strategy.on_bar()` sequentially
- Risk function called on every simulated order — **no bypass in backtesting**
- Outputs: Total return %, Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor
- Equity curve stored as JSON → overlaid on the same TradingView chart
- Historical data from `market_data_cache` or fetched live from Alpaca/yfinance

</details>

<details>
<summary><strong>📰 Market Intelligence</strong> — News + AI forecasting</summary>

- **News**: NewsAPI + Alpha Vantage, last 7 days per ticker
- **Sentiment**: scored by Claude Haiku (fast + cheap)
- **Forecast**: Prophet + ARIMA ensemble, 5-day horizon, 80% confidence band
- Always labeled: *"Statistical projection — not financial advice"*
- Shows model error metrics (MAE, MAPE) for transparency

</details>

<details>
<summary><strong>🛡️ Risk System</strong> — Non-negotiable, never bypassed</summary>

Six checks in order before any broker API call:
1. Market is currently open for this exchange
2. Symbol is on the strategy's allowed list
3. Order notional ≤ `max_order_notional`
4. Today's executed notional ≤ `max_daily_notional`
5. Total open positions ≤ tenant plan limit
6. Paper trading gate (live orders rejected if `paper_trading_only: true`)

`verify_order_intent()` is the single entry point. It is called in backtests too.

</details>

---

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND  (Next.js 14 App Router — Vercel)              │
│  /dashboard  /terminal/[symbol]  /strategies/*  /market  │
└───────────────────────┬──────────────────────────────────┘
                        │  REST + WebSocket (JWT Bearer)
┌───────────────────────▼──────────────────────────────────┐
│  CONTROL PLANE  (FastAPI + asyncpg — Hetzner CX32)       │
│  Auth · Strategies · Market Data · Portfolio · WS        │
└───────┬────────────────────────┬────────────────────────┘
        │ Celery (Redis broker)  │ Direct async calls
┌───────▼────────────┐   ┌───────▼──────────────────────┐
│  EXECUTION PLANE   │   │  INTELLIGENCE SERVICES        │
│  (Celery Workers)  │   │  market_data.py  (Alpaca/yf)  │
│                    │   │  indicators.py   (pandas-ta)  │
│  StrategyRunAgent  │   │  forecaster.py   (Prophet+ARIMA)│
│  RiskAgent (pure)  │   │  news_intel.py   (Claude Haiku)│
│  ExecutionAgent    │   │  backtester.py   (BacktestRunner)│
│  HeartbeatTask     │   └───────────────────────────────┘
└────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────┐
│  DATA LAYER                                               │
│  PostgreSQL 16 (primary store)  ·  Redis 7 (broker+pubsub)│
│  16 tables: strategies, runs, orders, positions,          │
│  portfolio_snapshots, market_data_cache, forecasts...     │
└──────────────────────────────────────────────────────────┘
```

**Infrastructure**: Hetzner CX32 (~€15/mo) + Cloudflare (free SSL/CDN) + Vercel (free frontend)

---

## Technology Choices

| Layer | Technology | Why This Specific Choice |
|-------|-----------|--------------------------|
| AI Agent Framework | [Microsoft AutoGen](https://github.com/microsoft/autogen) | NOT LangChain — see Engineering Decisions |
| AI Model | [Claude Sonnet 4.6](https://anthropic.com) | Strategy generation + market analysis |
| Technical Analysis | [pandas-ta](https://github.com/twopirllc/pandas-ta) | Pure Python — no TA-Lib compile failures |
| Forecasting | [Prophet](https://facebook.github.io/prophet/) + [statsmodels ARIMA](https://www.statsmodels.org/) | Ensemble with confidence intervals |
| Charts | [TradingView Lightweight Charts v4](https://tradingview.github.io/lightweight-charts/) | Only library with production-grade candlesticks |
| Code Editor | [Monaco Editor](https://microsoft.github.io/monaco-editor/) | VS Code engine in the browser |
| DB Driver | [asyncpg](https://github.com/MagicStack/asyncpg) | Fastest async PostgreSQL driver — raw SQL, no ORM |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | Version-controlled schema, async-compatible |
| Auth | [python-jose](https://github.com/mpdavis/python-jose) + [passlib](https://passlib.readthedocs.io/) | RS256 JWT + bcrypt — industry standard |
| Sandbox | [RestrictedPython](https://restrictedpython.readthedocs.io/) | Safe execution of user-submitted strategy code |
| Task Queue | [Celery 5](https://docs.celeryq.dev/) + Redis | Isolated workers per strategy. Battle-tested at scale. |
| US Market Data | [Alpaca](https://alpaca.markets/docs/) | Free paper trading + consistent data format |
| Indian Market Data | [yfinance](https://ranaroussi.github.io/yfinance/) | `RELIANCE.NS` / `RELIANCE.BO` — works reliably |
| Rate Limiting | [slowapi](https://github.com/laurentS/slowapi) | Per-endpoint, per-user on FastAPI |
| Monitoring | [Sentry](https://sentry.io/) | Production error + performance tracking |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker Desktop (for PostgreSQL + Redis)
- Node.js 18+ (for frontend)

### 1. Clone & Configure

```bash
git clone https://github.com/Algo-Ankit/AlphaSwarm.git
cd AlphaSwarm

# Copy and fill in your API keys
cp .env.example .env
```

Required environment variables in `.env`:

```bash
# Core infrastructure (defaults work with docker-compose)
DATABASE_URL=postgresql+asyncpg://alphaswarm:alphaswarm@localhost:5432/alphaswarm
DATABASE_SYNC_URL=postgresql://alphaswarm:alphaswarm@localhost:5432/alphaswarm
REDIS_URL=redis://localhost:6379/0

# AI (get at console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-...

# Alpaca (free paper account at alpaca.markets)
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# JWT — for dev, only JWT_SECRET_KEY is needed (HS256 fallback)
# For production, generate RS256 keys (see .env.example for commands)
JWT_SECRET_KEY=your-dev-secret-change-in-production
```

### 2. Start Infrastructure

```bash
# Starts PostgreSQL 16, Redis 7, and Adminer (DB UI at localhost:8080)
docker compose up -d
```

### 3. Run Migrations

```bash
pip install -r requirements.txt
alembic upgrade head
```

### 4. Start the API

```bash
uvicorn app.main:app --reload
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 5. Start Celery Workers

```bash
# In separate terminals:
celery -A app.core.celery_app.celery_app worker -Q trading_tasks -c 2 --loglevel=info
celery -A app.core.celery_app.celery_app beat --loglevel=info
```

### 6. Start the Frontend

```bash
cd frontend
npm install
npm run dev
# Available at http://localhost:3000
```

### Quick API Smoke Test

**Register a new account:**
```bash
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "trader@example.com",
    "password": "securepassword",
    "display_name": "Test Trader",
    "tenant_name": "My Trading Firm"
  }'
```

**Login:**
```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "trader@example.com", "password": "securepassword"}'
# Returns: {"access_token": "eyJ...", "refresh_token": "..."}
```

**Create a strategy:**
```bash
curl -X POST http://localhost:8000/v1/strategies \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SPY Momentum",
    "prompt": "Buy SPY when RSI(14) drops below 30. Sell when RSI crosses above 70.",
    "symbols": ["SPY"],
    "timeframe": "1h"
  }'
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/v1/auth/register` | — | Create tenant + owner account |
| `POST` | `/v1/auth/login` | — | Email/password → JWT tokens |
| `POST` | `/v1/auth/refresh` | — | Rotate refresh token → new access token |
| `POST` | `/v1/auth/logout` | Bearer | Invalidate refresh token |
| `POST` | `/v1/strategies` | Bearer | Create strategy (NL or code) |
| `GET` | `/v1/strategies` | Bearer | List all tenant strategies |
| `GET` | `/v1/strategies/{id}` | Bearer | Strategy detail |
| `POST` | `/v1/strategies/{id}/runs` | Bearer | Deploy strategy (paper or live) |
| `GET` | `/v1/tasks/{task_id}` | Bearer | Celery task status |
| `GET` | `/health` | — | Liveness probe |
| `GET` | `/health/ready` | — | Readiness probe (checks DB + Redis) |

> Full OpenAPI spec: [`openapi.json`](openapi.json) — or visit `/docs` when running locally.

**Upcoming in Phase 3:**
`GET /v1/market/bars/{symbol}` · `/indicators/{symbol}` · `/forecast/{symbol}` · `/news/{symbol}` · `/search`

---

## Security Architecture

```
Access Token:   RS256 JWT · 15-minute expiry · sub=user_id + tenant_id + role
Refresh Token:  32-byte random · SHA-256 hashed in DB · 30-day expiry · rotated on use
Multi-tenancy:  Every SQL query has WHERE tenant_id = $N · enforced in repository layer
Broker Keys:    Fernet AES-128-CBC encrypted at rest · decrypted in memory only
Dev Mode:       HS256 fallback (no key generation required) · set JWT_SECRET_KEY only
Code Sandbox:   RestrictedPython · no os/subprocess/socket imports · 30s timeout
```

---

## Engineering Decisions

These are the non-obvious choices made and why. Each one resolved a real constraint.

### 1. Microsoft AutoGen — not LangChain

**Decision**: Use [Microsoft AutoGen](https://github.com/microsoft/autogen) for all AI agent orchestration.

**Why not LangChain**: LangChain ships breaking API changes in minor versions. In early prototyping, an upgrade from `0.1.x` to `0.2.x` broke the agent chain with no deprecation notice. A trading system that breaks on `pip install --upgrade` is not deployable. AutoGen's multi-agent API has been stable since its public release and is production-deployed at Microsoft.

**Result**: `StrategyBuilderAgent`, `StrategyRunAgent`, `ExecutionAgent`, `AnalysisAgent` — all AutoGen. LangChain imports are banned in this codebase.

---

### 2. pandas-ta — not TA-Lib

**Decision**: Use [pandas-ta](https://github.com/twopirllc/pandas-ta) for all technical indicators.

**Why not TA-Lib**: TA-Lib requires compiling a C extension. On Windows it requires Visual Studio Build Tools. On Alpine Linux (used in Docker) it requires `build-essential` and custom wheel builds. This adds 15+ minutes to CI and breaks for new contributors on fresh machines. pandas-ta is pure Python, installs in seconds on any OS, and covers every indicator we need (RSI, MACD, Bollinger, EMA, VWAP, ATR, Stochastic).

**Result**: Zero compile-step indicators. `pip install pandas-ta` just works.

---

### 3. Raw asyncpg — not SQLAlchemy ORM

**Decision**: Use [asyncpg](https://github.com/MagicStack/asyncpg) with raw SQL, not SQLAlchemy ORM.

**Why**: Financial data access patterns are known and stable — we write specific queries, not dynamic ones. Raw asyncpg is 3-5x faster than SQLAlchemy async ORM for the read-heavy workloads in trading (fetching 500 bars, indicator computation, order history). The repository pattern with explicit `tenant_id` enforcement gives us better security than ORM-level row-level security. Alembic handles migrations fine without ORM models.

**Result**: Sub-millisecond DB calls for market data fetches. Explicit tenant isolation impossible to accidentally bypass.

---

### 4. TradingView Lightweight Charts — not Recharts or Chart.js

**Decision**: Use [TradingView Lightweight Charts v4](https://tradingview.github.io/lightweight-charts/) exclusively.

**Why**: We evaluated Recharts, Chart.js, Victory, Nivo, and D3. None support candlestick charts with proper OHLC rendering, sub-charts (RSI/MACD panes), and the ~500ms paint time needed for a real-time terminal. TradingView Lightweight Charts is what TradingView itself uses for its lightweight embeds. It renders 10,000 candles in milliseconds via canvas. It's the only library in this space worth using.

**Result**: Professional candlestick + TA terminal. No compromises on chart quality.

---

### 5. NSEpy is banned — use yfinance for Indian data

**Decision**: NSEpy is explicitly banned. Use `yfinance` with `.NS` / `.BO` suffixes for all Indian market data.

**Why**: NSEpy depended on undocumented NSE website scraping endpoints that NSE changed their infrastructure and removed. NSEpy returns empty DataFrames or HTTP 403s on current NSE infrastructure. Every project that used NSEpy for Indian EOD data is now broken. yfinance's `RELIANCE.NS` (NSE) and `RELIANCE.BO` (BSE) format works reliably for daily/weekly data.

**Result**: `import NSEpy` is a hard ban. Any agent or contributor attempting to use it gets rejected at code review.

---

### 6. BYOB (Bring Your Own Broker) — no custody

**Decision**: AlphaSwarm never holds or touches trader funds. All money stays in the trader's own regulated broker account.

**Why**: Holding or transmitting customer funds requires money transmission licenses in every jurisdiction you operate in. The regulatory and compliance overhead would dwarf the engineering cost and make the startup unlaunachable without significant legal infrastructure. BYOB means: trader deposits in their Zerodha/Alpaca account, gives AlphaSwarm API keys, AlphaSwarm sends orders on their behalf. AlphaSwarm is software, not a broker.

**Result**: Launch without any financial licensing. Revenue comes from SaaS subscriptions, not from managing funds.

---

### 7. Hetzner + Cloudflare + Vercel — not AWS

**Decision**: Hetzner CX32 for compute, Cloudflare for CDN/DDoS, Vercel for frontend.

**Why**: An AWS EC2 `t3.large` + RDS + ElastiCache costs ~$250/month minimum. A Hetzner CX32 (4 vCPU, 8 GB RAM) costs €15/month and runs the full stack (API + workers + PostgreSQL + Redis). Cloudflare's free tier handles SSL termination, DDoS protection, and CDN. Vercel's free tier handles Next.js deployment natively. Total infra cost at launch: ~€15/month. This matters for a bootstrapped startup.

**Result**: Production-grade infra at startup pricing. Upgrade path: add Hetzner boxes as load requires.

---

## Issues Encountered & Resolved

Real problems that came up during development and how they were fixed.

| # | Issue | Root Cause | Resolution |
|---|-------|-----------|------------|
| 1 | **Strategy data lost on every restart** | `StrategyStore` was an in-memory Python dict | Phase 2: replaced with PostgreSQL via `StrategyRepo` + asyncpg pool |
| 2 | **Alembic couldn't connect without psycopg2** | Alembic's default sync driver requires psycopg2; we only have asyncpg | Used SQLAlchemy 2.0 async engine via `async_engine_from_config` in `alembic/env.py` — no psycopg2 needed |
| 3 | **JWT dev setup required key generation commands** | RS256 requires RSA key pair; new devs would hit auth errors immediately | Added HS256 fallback in `app/services/auth.py` — if `JWT_PRIVATE_KEY` not set, falls back to `JWT_SECRET_KEY` for HS256. Dev works out of the box. |
| 4 | **Tenant isolation could be accidentally bypassed** | Route-layer tenant filtering is easy to forget | Enforced at repository layer in `BaseRepo` — `tenant_id` is set at construction, every query must use `self.tenant_id`. |
| 5 | **JSONB columns returned as strings in asyncpg** | asyncpg doesn't register a JSONB decoder by default | Registered a custom codec in `_init_connection`: `set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads)` |
| 6 | **Strategy versioning FK cycle** | `strategies.current_version_id` FK to `strategy_versions`, which FKs back to `strategies` | Created strategy first, then version, then updated `current_version_id` in a single transaction. FK added as `ALTER TABLE` after both tables exist. |
| 7 | **NSEpy returns empty data** | NSE changed their infrastructure | Hard-banned NSEpy across the codebase. `yfinance` with `.NS`/`.BO` suffix is the replacement. |

---

## Build Status & Roadmap

```
Phase 0  [██████████] System Design v2.0 — complete, all gaps resolved
Phase 1  [██████████] Backend Foundation — FastAPI, Celery, Docker, Nginx, Pydantic models
Phase 2  [██████████] DB Layer + Auth — asyncpg pool, Alembic, repositories, JWT RS256/HS256
Phase 3  [░░░░░░░░░░] Market Data & Intelligence — NEXT
Phase 4  [░░░░░░░░░░] Execution Engine — AutoGen agents, Alpaca broker, crash recovery
Phase 5  [░░░░░░░░░░] Strategy Builder + Backtesting — NL→code, BacktestRunner, sandbox
Phase 6  [░░░░░░░░░░] Frontend — TradingView terminal, auth pages, dual-path builder
Phase 7  [░░░░░░░░░░] Production Hardening — rate limiting, Sentry, billing, live gate
```

### Phase 3 — What's next

- `app/services/market_data.py` — Alpaca Data API (US) + yfinance (Indian/global), normalized to canonical `Bar` model
- `app/services/indicators.py` — pandas-ta, parameterized: `rsi(14)`, `macd(12,26,9)`, `bb(20,2)`, `ema(200)`, `vwap`
- `app/services/forecaster.py` — Prophet + ARIMA ensemble, cached in `forecasts` table
- `app/services/news_intel.py` — NewsAPI + Alpha Vantage + Claude Haiku sentiment scoring
- REST endpoints: `GET /v1/market/bars/{symbol}`, `/indicators/{symbol}`, `/forecast/{symbol}`, `/news/{symbol}`
- WebSocket infrastructure: Redis pub/sub + FastAPI WS manager + Alpaca live feed
- Celery Beat tasks: portfolio snapshots, news refresh, forecast regeneration

---

## Monetization Model

**AlphaSwarm is launching with a Founding Member program** — first 500 users get full access free, forever (within the founding tier).

| Tier | Bots | Markets | Price |
|------|------|---------|-------|
| **Founding Member** | 5 | Paper + Live | **Free** (500 spots) |
| Trader *(coming soon)* | 5 | Paper + Live | INR 999/mo · $15/mo |
| Pro *(coming soon)* | 20 | All global | INR 2999/mo · $49/mo |
| Quant *(coming soon)* | Unlimited | All + API | INR 7999/mo · $99/mo |

Payments: **Stripe** (international) · **Razorpay** (India / UPI)

---

## Market Coverage

| Market | Source | Notes |
|--------|--------|-------|
| US (NASDAQ, NYSE) | Alpaca Data API | Free with paper account |
| Indian EOD (NSE, BSE) | yfinance (`RELIANCE.NS`, `RELIANCE.BO`) | Reliable daily/weekly data |
| Indian Intraday (NSE) | Zerodha Kite Connect / Upstox | User provides own broker credentials |
| Crypto | Alpaca Crypto | Same format as equities |
| Global | yfinance | All other tickers |

> ⚠️ NSEpy is **permanently banned** in this codebase. It fails on current NSE infrastructure.

---

## Supported Brokers at Launch

| Broker | Status | Connection Method |
|--------|--------|-------------------|
| **Alpaca** | ✅ Launch | 3-step guided wizard |
| **Upstox** | ✅ Launch | OAuth one-click |
| Zerodha | 🔜 Post-launch | OAuth (after developer fee ROI) |
| Fyers | 🔜 Post-launch | OAuth |

---

## Project Structure

```
AlphaSwarm/
├── app/
│   ├── api/
│   │   ├── auth.py          # POST /v1/auth/{register,login,refresh,logout}
│   │   ├── deps.py          # JWT dependency injection → CurrentUser
│   │   └── routes.py        # Strategy CRUD + run dispatch
│   ├── core/
│   │   ├── config.py        # pydantic-settings — all env vars
│   │   └── celery_app.py    # Celery + Beat config
│   ├── db/
│   │   ├── connection.py    # asyncpg pool + JSONB codec
│   │   ├── base_repo.py     # Tenant-scoped base repository
│   │   └── repositories/
│   │       ├── users.py     # TenantRepo, AuthUserRepo, RefreshTokenRepo, UserRepo
│   │       ├── strategies.py # StrategyRepo (CRUD + versioning)
│   │       └── runs.py      # RunRepo (lifecycle management)
│   ├── domain/
│   │   ├── base_strategy.py # BaseStrategy interface (all strategies subclass this)
│   │   ├── market_data.py   # Canonical Bar model + Exchange enum
│   │   ├── market_hours.py  # Exchange schedules + is_market_open()
│   │   ├── models.py        # All Pydantic request/response models
│   │   └── risk.py          # verify_order_intent() — never bypassed
│   ├── services/
│   │   ├── auth.py          # JWT sign/verify + bcrypt + refresh tokens
│   │   └── strategy_compiler.py  # Stub → replaced by AutoGen in Phase 5
│   ├── worker/
│   │   ├── tasks.py         # Celery tasks (stub → real in Phase 4)
│   │   └── beat_tasks.py    # Scheduled tasks (stubs)
│   └── main.py              # FastAPI app, lifespan, middleware, health checks
├── alembic/
│   ├── env.py               # Async migration environment (asyncpg via SQLAlchemy)
│   └── versions/
│       └── 0001_initial_schema.py  # All 16 tables
├── frontend/                # Next.js 14 App Router (Phase 6)
├── nginx/nginx.conf         # Least-conn LB, rate limiting, WS upgrade
├── docker-compose.yml       # Local: postgres + redis + adminer
├── docker-compose.prod.yml  # Prod: nginx + 3x API + 2x worker + beat
├── Dockerfile               # Multi-stage, non-root, uvloop
├── schema.sql               # Reference schema (source of truth for migrations)
├── ARCHITECTURE.md          # Complete system design — read before coding
└── requirements.txt         # All 30+ dependencies
```

---

## Contributing

AlphaSwarm is being built as a startup MVP. Architecture decisions are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md) — **read it in full before writing any code**.

**Hard rules for contributors:**
- No LangChain — AutoGen only
- No NSEpy — yfinance only
- No TA-Lib — pandas-ta only
- `verify_order_intent()` must be called before every broker API call, always
- Every DB query must include `tenant_id` filter — enforced in `BaseRepo`, never bypass it
- Every chart must answer a specific question. No decorative charts.

```bash
# Run tests (coming in Phase 3)
pytest

# Lint
ruff check .

# Type check
mypy app/
```

---

## Deployment

### Local Development
```bash
docker compose up -d          # infrastructure
alembic upgrade head           # run migrations
uvicorn app.main:app --reload  # API
```

### Production (Hetzner)
```bash
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --scale api=3 --scale worker=2
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

**Infrastructure stack**: Hetzner CX32 → Nginx (LB + rate limiting + WS) → 3x FastAPI containers → 2x Celery workers + 1x Beat → PostgreSQL 16 + Redis 7

---

## License

MIT © 2026 AlphaSwarm — Built by [Ankit Anand Singh](https://github.com/Algo-Ankit)

---

<div align="center">

**AlphaSwarm is being built in public.**  
Star the repo to follow the journey from infrastructure to a full trading terminal.

[![GitHub Stars](https://img.shields.io/github/stars/Algo-Ankit/AlphaSwarm?style=social)](https://github.com/Algo-Ankit/AlphaSwarm)

*Phase 2 complete. Phase 3 (Market Data & Intelligence) in progress.*

</div>
