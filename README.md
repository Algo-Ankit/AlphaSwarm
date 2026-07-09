<div align="center">

```
 █████╗ ██╗     ██████╗ ██╗  ██╗ █████╗ ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
██╔══██╗██║     ██╔══██╗██║  ██║██╔══██╗██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
███████║██║     ██████╔╝███████║███████║███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
██╔══██║██║     ██╔═══╝ ██╔══██║██╔══██║╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
██║  ██║███████╗██║     ██║  ██║██║  ██║███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
```

### **Your AI quant team, in a browser tab.**

*Describe a strategy in plain English — or set a goal like "retire by 50."*
*AlphaSwarm's AI writes the code, backtests it against institutional-grade reality, and trades it through **your own broker**.*
*A pro trading terminal, a wealth-management copilot, and a GitHub-style commons of forkable strategies — with zero infrastructure and no Bloomberg subscription.*

---

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Agent Framework](https://img.shields.io/badge/Microsoft_Agent_Framework-1.x-5E5CE6?style=flat-square&logo=microsoft&logoColor=white)](https://github.com/microsoft/agent-framework)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[![Status](https://img.shields.io/badge/Status-MVP_Live-success?style=flat-square)](https://github.com/Algo-Ankit/AlphaSwarm)
[![Founding Members](https://img.shields.io/badge/Founding_Members-Open-gold?style=flat-square)](https://github.com/Algo-Ankit/AlphaSwarm)

</div>

---

## ⚡ The 30-Second Pitch

Building an algorithmic trading strategy today means hiring a quant, writing Python, wiring up market data, backtesting it honestly, managing risk, and babysitting a server. **AlphaSwarm collapses that entire stack into a sentence.**

> 🗣️ *"Buy RELIANCE when RSI(14) drops below 30 and price is above the 200-day EMA. Take profit at 8%."*

You type that. AlphaSwarm's AI generates a validated, sandboxed Python strategy, backtests it with **real-world slippage and market-impact modelling**, and — once you connect your own broker — deploys it. Prefer something simpler? Tell the **Goal Wizard** *"I want ₹50L for retirement in 20 years"* and it builds a SIP portfolio. Want to learn from others? Browse the **Swarm** — a commons of forkable, honestly-scored strategies.

**We never touch your money.** Your funds stay in your own Zerodha / Upstox / Angel One / Alpaca account. AlphaSwarm is software that sends orders on your behalf — not a broker, not a fund. That is the entire trust model.

| Who | What they get |
|-----|----------------|
| 🧑‍💼 **Retail investor** | A Goal Wizard, SIPs you can pause/resume, XIRR & allocation dashboards, a wealth-management AI copilot — no code, ever. |
| 📈 **Active trader** | A Bloomberg-style terminal: candles, RSI/MACD/Bollinger, news, AI forecasts, live P&L over WebSockets. |
| 🧑‍🔬 **Quant developer** | A browser Monaco editor, a hardened Python sandbox, a prop-grade backtester, and a forkable strategy commons. |

> 📚 **Want to actually understand the system — enough to teach or pitch it?**
> - 🖥️ **[Read the visual documentation site →](https://algo-ankit.github.io/AlphaSwarm/)** — a designed, single-page tour of the architecture (live once GitHub Pages is enabled; source in [`docs/index.html`](docs/index.html)).
> - 📖 **[The Definitive Handbook](AlphaSwarm_The_Definitive_Guide.md)** — how every subsystem works under the hood, the finance concepts explained in plain English, end-to-end data-flow walkthroughs, and ready-made 60-second / 5-minute / whiteboard explanations.

---

## 🎯 Why traders should trust it

- **🔒 No custody, no licence risk.** Bring Your Own Broker (BYOB). Your capital never leaves your regulated broker account.
- **🛡️ A risk engine that cannot be bypassed.** `verify_order_intent()` runs before *every* order — in live trading **and** in backtests. Same code path, no exceptions. Protected by transactional 64-bit advisory locks against race conditions.
- **🔑 Bring Your Own Key (BYOK).** The AI runs on *your* free API key (Groq, Gemini, OpenRouter, or local Ollama). We ship no hidden paid key and never bill you for tokens.
- **🧪 Honest backtests.** Most retail backtesters lie — they fill stop-losses at the stop price and assume infinite liquidity. Ours models adverse gap fills, a 10% volume-participation cap (Almgren–Chriss), bid/ask reality, commissions, and short-borrow financing.
- **📉 An honest marketplace.** Published strategies carry an **out-of-sample scorecard** — automatically backtested on data *after* their publish date — so decayed alpha is shown, not hidden.
- **🔐 Real security.** RestrictedPython sandbox hardened against RCE & DoS, HKDF/Fernet envelope encryption for broker keys, RS256 JWT, strict per-tenant SQL isolation. See [Security](#-security-architecture).

---

## 🧩 Core Product Modules

<details>
<summary><strong>🤖 AI Strategy Builder</strong> — Natural language → deployable Python</summary>

- Powered by the **Microsoft Agent Framework** (ReAct pattern) + your BYOK model.
- Multi-turn: the agent generates code, validates it against the live sandbox tool, self-critiques, and fixes itself.
- Output is always a validated `BaseStrategy` subclass. The user sees a plain-English explanation; the code hides behind a "Show Code" toggle.
- Failure contract: always returns `{error, suggestion}` — never silently emits broken code.

</details>

<details>
<summary><strong>🧠 AI Investment Advisor</strong> — A wealth-management copilot</summary>

- A conversational advisor for stock/ETF analysis and SIP/SWP planning, rendered as safe sanitized markdown.
- **Retrieval-augmented on the commons**: when you describe a thesis, the most relevant published strategies are pulled in as few-shot grounding — every published strategy makes the advisor smarter.
- Same strict BYOK enforcement as the builder (your key, or a founder-only platform fallback).

</details>

<details>
<summary><strong>🐝 The Swarm — a strategy commons</strong> — GitHub for trading strategies</summary>

- **Immutable published versions.** Publishing pins the exact strategy version — what people copy or fork is a frozen snapshot, not an editable post.
- **Fork graph.** Fork any listing into your own workspace; the lineage — *"the strategy 400 people forked, and the mutations that beat it"* — is a live graph.
- **Copy trading.** Subscribe to a listing and its signals fan out into **your own** broker account, sized to the capital you allocate. The platform never pools funds.
- **Anti-survivorship gates.** Publishing requires ≥ 3 on-platform backtests, and each listing gets a recomputed out-of-sample scorecard so overfit winners can't masquerade as skill.
- **Social feed + Swarm Tax.** A creator timeline plus a 1% monthly Swarm Tax on copied capital, split 50/50 between platform and creator.

</details>

<details>
<summary><strong>🎯 Goal-Based Investing & SIPs</strong> — Wealth-tech for everyone</summary>

- **Goal Wizard**: pick a goal (retirement, education) → risk profile → horizon → AlphaSwarm pre-fills a strategy.
- **SIP controls**: pause/resume any SIP, fire a lump-sum boost, approve rebalances from the notifications panel.
- **Dashboards built for investors, not just traders**: XIRR (Newton–Raphson) and an asset-allocation donut chart instead of raw P&L.
- **Unified wealth view**: import holdings from multiple brokers (CAS ingestion) and see a Monte Carlo / GBM wealth projection across your whole portfolio.

</details>

<details>
<summary><strong>📊 Trading Terminal</strong> — The pro screen</summary>

- Candlesticks via **TradingView Lightweight Charts v4**; timeframes 1m → 1W.
- Overlays: 20/50/200 EMA, Bollinger Bands, VWAP. Sub-charts: RSI(14), MACD, Volume.
- Parameterizable at runtime — `rsi(21)`, `macd(5,35,5)`, `bb(20,2.5)`.
- All indicators computed **server-side** with `pandas-ta`; the client only renders.

</details>

<details>
<summary><strong>📈 Institutional-Grade Backtester</strong> — Same risk checks as live</summary>

- Replays historical OHLCV through `strategy.on_bar()` — the risk engine runs on every simulated order.
- Models **adverse gap fills**, **10% volume-participation cap**, **bid/ask spread**, **commission-aware** profit factor & win rate, **short-borrow financing**, and terminal-liquidation costs.
- Outputs Total Return, Sharpe, **Sortino (true RMS downside deviation)**, Max Drawdown, Calmar, Win Rate, Profit Factor.
- Equity curve overlays onto the same TradingView chart.

</details>

<details>
<summary><strong>📰 Market Intelligence</strong> — News + AI forecasting</summary>

- News (NewsAPI + Alpha Vantage) with AI sentiment scoring.
- Forecast: Prophet + ARIMA ensemble, 5-day horizon, 80% confidence band — always labelled *"Statistical projection, not financial advice"* with MAE/MAPE shown.

</details>

<details>
<summary><strong>🛡️ The Risk System</strong> — Non-negotiable</summary>

Six checks, in order, before any broker API call (and in every backtest):
1. Market open for this exchange &nbsp; 2. Symbol on the allowed list &nbsp; 3. Order notional ≤ cap
4. Daily executed notional ≤ cap &nbsp; 5. Open positions ≤ plan limit &nbsp; 6. Paper-trading gate

`verify_order_intent()` is the single entry point. There is no second door.

</details>

---

## 🔑 Signing In — five ways, zero friction

AlphaSwarm meets each user where they are. Every path lands on the same session:

| Method | Best for | Notes |
|--------|----------|-------|
| **Email + password** | Everyone | With email verification, password reset, and refresh-token rotation. |
| **Continue with Google** | Fast onboarding & admin testing | Pure identity (connects no brokerage); trusts Google's verified-email claim. |
| **Email / phone OTP** | Users who prefer a code | One field takes an email *or* a mobile number; new accounts are created on first verified code. In dev the code is logged, so you can test with no SMS gateway. |
| **Continue with Upstox** | Indian traders | One click authenticates **and** connects the brokerage for live execution — no API keys to copy. |
| **Broker keys (Zerodha / Angel One / Alpaca)** | Power users | Encrypted at rest with an HKDF/Fernet envelope. |

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND  (Next.js 14 App Router — Vercel)               │
│  /dashboard /terminal /strategies/* /leaderboard /advisor │
│  /portfolio /feed /settings/*  /login (+ OTP / OAuth)     │
└───────────────────────┬──────────────────────────────────┘
                        │  REST + WebSocket (JWT Bearer)
┌───────────────────────▼──────────────────────────────────┐
│  CONTROL PLANE  (FastAPI + asyncpg — Hetzner)             │
│  Auth · Strategies · Market · Portfolio · Brokers/OAuth   │
│  Social (Swarm) · Feed · AI Advisor · Billing · Notifs    │
│  Billing (Stripe+Razorpay) · WebSocket fan-out            │
└───────┬────────────────────────┬─────────────────────────┘
        │ Celery (Redis broker)  │ Direct async calls
┌───────▼────────────┐   ┌───────▼──────────────────────────┐
│  EXECUTION PLANE   │   │  INTELLIGENCE SERVICES            │
│  (Celery Workers)  │   │  market_data · indicators (TA)    │
│  StrategyRunAgent  │   │  forecaster (Prophet+ARIMA)       │
│  Risk (pure func)  │   │  news_intel · backtest            │
│  ExecutionAgent    │   │  oauth_manager · strategy_builder │
│  SIP · Heartbeat   │   │  ai_advisor · forecasting (GBM)   │
│  Swarm Tax · OOS   │   │  (Microsoft Agent Framework)      │
└────────────────────┘   └───────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────┐
│  DATA LAYER                                               │
│  PostgreSQL 16 (primary)  ·  Redis 7 (broker + pub/sub)  │
│  Sentry (errors) · SendGrid (email) · Twilio (SMS OTP)   │
└──────────────────────────────────────────────────────────┘
```

**Infrastructure**: Hetzner (~€15/mo) + Cloudflare (free SSL/CDN) + Vercel (free frontend). Production-grade at bootstrap pricing.

---

## 🛠️ Technology Choices (and why)

| Layer | Tech | The reason |
|-------|------|-----------|
| AI orchestration | **Microsoft Agent Framework** | Stable API; migrated off AutoGen (maintenance-only). LangChain is banned — it ships breaking changes in minor versions. |
| AI model | **BYOK** (Groq / Gemini / OpenRouter / Ollama / Claude) | Users bring a free key. No shipped paid key, no token billing. |
| Technical analysis | **pandas-ta** | Pure Python — no TA-Lib C-compile pain across OSes. |
| Forecasting | **Prophet + statsmodels ARIMA**, GBM Monte Carlo | Ensemble with confidence intervals; wealth projection over whole portfolios. |
| Charts | **TradingView Lightweight Charts v4** + Chart.js | Prop-grade candlesticks + sub-charts; Chart.js for wealth projections. |
| Code editor | **Monaco** | The VS Code engine, in the browser. |
| DB driver | **asyncpg** (raw SQL, no ORM) | 3–5× faster for our read-heavy workloads; explicit `tenant_id` isolation. |
| Migrations | **Alembic** (async) | Version-controlled schema, asyncpg-native. |
| Auth | **python-jose + passlib** | RS256 JWT + bcrypt; Google / Upstox OAuth; stateless OTP + action tokens. |
| Sandbox | **RestrictedPython** | Hardened safe execution of user strategy code. |
| Queue | **Celery 5 + Redis** | Isolated workers per strategy + periodic beat tasks. |
| Market data | **Alpaca** (US/crypto) · **yfinance** (`.NS`/`.BO`) · **Upstox/Zerodha** (live India) | NSEpy is permanently banned — broken on current NSE infra. |
| Billing | **Stripe (USD) + Razorpay (INR/UPI)** | Dual-gateway, gates live deployment. |
| Ops | **Sentry · SendGrid · Twilio · GitHub Actions** | Errors, email, SMS OTP, CI. |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+ · Docker Desktop · Node.js 18+

### 1. Clone & configure
```bash
git clone https://github.com/Algo-Ankit/AlphaSwarm.git
cd AlphaSwarm
cp .env.example .env   # fill in your keys — see .env.example for the full annotated list
```
Minimum to run locally (defaults work with docker-compose):
```bash
DATABASE_URL=postgresql+asyncpg://alphaswarm:alphaswarm@localhost:5432/alphaswarm
DATABASE_SYNC_URL=postgresql://alphaswarm:alphaswarm@localhost:5432/alphaswarm
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=dev-secret-change-in-production   # HS256 dev fallback, no key-gen needed

# BYOK AI — point at a FREE provider (Groq shown) or a local Ollama; no paid key required
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=<your-free-groq-key>
LLM_MODEL=llama-3.1-8b-instant

# Alpaca paper account (free) for US market data + paper trading
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```
> **Optional integrations are no-ops until configured** — SendGrid (email), Twilio (SMS OTP), Google / Upstox OAuth, Stripe / Razorpay, and Sentry all degrade gracefully. In dev, login OTPs are written to the server log so you can sign in with no gateway at all.

### 2. Infra → migrate → API
```bash
docker compose up -d                 # PostgreSQL 16 + Redis 7 (+ Adminer at :8080)
pip install -r requirements.txt
alembic upgrade head                 # applies migrations 0001 → 0014
uvicorn app.main:app --reload        # API at http://localhost:8000  ·  docs at /docs
```

### 3. Workers
```bash
celery -A app.core.celery_app.celery_app worker -Q trading_tasks,beat_tasks -c 2 --loglevel=info
celery -A app.core.celery_app.celery_app beat --loglevel=info
```

### 4. Frontend
```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

### Smoke test
```bash
# Register → returns a session; then log in for a token
curl -X POST http://localhost:8000/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email":"trader@example.com","password":"securepassword","display_name":"Test","tenant_name":"My Firm"}'

curl -X POST http://localhost:8000/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"trader@example.com","password":"securepassword"}'   # → {access_token, refresh_token}

# Passwordless: request an OTP (dev logs the code to the server console), then verify it
curl -X POST http://localhost:8000/v1/auth/otp/request -H "Content-Type: application/json" \
  -d '{"identifier":"trader@example.com"}'
```

---

## 🔐 Security Architecture

```
Access token   RS256 JWT · 15-min expiry · sub = user_id + tenant_id + role  (HS256 dev fallback)
Refresh token  32-byte random · SHA-256 hashed in DB · 30-day · rotated on use, reuse-detected
Action tokens  stateless signed JWTs for password reset / email verify — reset embeds a hash of
               the current password so the link self-invalidates the moment the password changes
Login OTPs     only sha256(code) stored · single-use · attempt-capped · resend-throttled
Multi-tenancy  every query carries WHERE tenant_id = $N · enforced in BaseRepo, impossible to skip
Broker keys    HKDF + Fernet envelope encryption at rest · decrypted in memory only
OAuth          signed-token CSRF on every flow · Indian broker tokens auto-refresh via retry_on_401
Code sandbox   RestrictedPython · str-subclass guard · format denylist · iter DoS removed · exec timeout
LLM access     strict BYOK · founder-only platform-key fallback gated by timing-safe email compare
```

---

## 🧠 Engineering Decisions

The non-obvious calls, each resolving a real constraint:

1. **Microsoft Agent Framework, not LangChain.** LangChain breaks on minor upgrades — unacceptable for a trading system. We even migrated *off* AutoGen once it went maintenance-only.
2. **pandas-ta, not TA-Lib.** No C-compile step; installs in seconds on any OS.
3. **Raw asyncpg, not an ORM.** 3–5× faster on our read-heavy paths; explicit tenant isolation.
4. **TradingView charts, not Recharts/Chart.js for candles.** The only library that renders 10k candles + sub-charts at terminal speed.
5. **yfinance, not NSEpy.** NSEpy depends on dead NSE scraping endpoints. Hard-banned.
6. **BYOB — no custody.** Launch with zero money-transmission licensing. Revenue is SaaS, not AUM.
7. **Immutable published versions + a fork graph, not editable posts.** The value of a commons is lineage; what people fork must be a frozen snapshot.
8. **Out-of-sample scorecards on every listing.** Without them a public leaderboard degenerates into a survivorship-biased lottery gallery.
9. **Hetzner + Cloudflare + Vercel, not AWS.** ~€15/mo vs ~$250/mo for the same capability.

---

## 🐛 Battle Scars — Bugs Found & Fixed

The git history reads like a postmortem. Highlights:

| Area | The bug | The fix |
|------|---------|---------|
| Persistence | Strategies lost on every restart (in-memory dict) | PostgreSQL via tenant-scoped repositories |
| Metrics | `OverflowError` on short-window CAGR; wrong Sortino math | Edge-case-hardened metrics, true RMS downside deviation |
| Realtime | Sync Redis `.publish()` blocked the ASGI loop; WS race overwrote live data | Async client; merge-not-replace state |
| Concurrency | **TOCTOU double-fills** under concurrent signals | `pg_advisory_xact_lock` (64-bit) with position reads *inside* the transaction |
| Security | **Sandbox RCE/DoS** via str-subclassing, `iter(int,1)`, `.format` maps | Guarded getattr, type checks, format denylist, `ReadOnlyDataFrame`, exec timeout |
| Data model | Schema could orphan active SIPs (`ON DELETE SET NULL`) | `tenant_id` on mandates, strict `CHECK` constraints, normalized OAuth fields |
| Backtester | Filled gapped stop-losses at the stop price | Adverse-gap fills, volume-participation cap, bid/ask + cost realism |
| Billing | Phantom revenue on unverified webhooks; Razorpay race | Verified-signature gating, idempotent subscription state |

---

## 🗺️ Roadmap

```text
Phase 0    [██████████] System design v2.0
Phase 1-2  [██████████] Backend, DB layer, multi-tenant JWT auth
Phase 3-4  [██████████] Market data + execution engine + zero-bypass risk
Phase 5    [██████████] AI strategy builder + sandbox + backtesting
Phase 6    [██████████] Next.js terminal, WebSockets, live P&L
Phase 7    [██████████] Production hardening — security & concurrency audit
Phase 8    [██████████] Wealth-tech — Goal Wizard, XIRR, multi-broker OAuth, SIPs
Phase 9    [██████████] Institutional backtester — slippage, market impact, cost realism
Phase 10   [██████████] Go-to-market — Stripe + Razorpay billing, SendGrid, Sentry, CI/CD, live Upstox
Phase 11   [██████████] The Swarm — copy trading, AI advisor, unified portfolio, social feed
Phase 12   [█████████░] Strategy Commons — fork graph, immutable versions, OOS honesty, OTP/Google auth
```

### 🔮 What's next

- **Tax-Loss Harvesting Engine** — FIFO lot accounting + automated harvesting around India's ₹1.25L LTCG exemption.
- **Account Aggregator (RBI AA) integration** — consented pull of external MF/stock holdings for holistic AI advice.
- **Corporate-actions pipeline** — auto-adjust for splits, bonuses, dividends, mergers.
- **e-NACH / UPI AutoPay mandates** — fully automated SIP funding (Razorpay/Digio).
- **Centralized feed handler (TimescaleDB)** — multiplex one data stream to thousands of users.
- **SEBI peak-margin & circuit-limit awareness** — cleared-vs-uncleared cash, pre-open session orders.

---

## 💳 Monetization

**Founding Member program at launch** — early users get full access while we grow.

| Tier | What it unlocks | Price |
|------|------------------|-------|
| **Free / BYOK** | AI builder & advisor, paper trading, full backtester, terminal, goal wizard, the Swarm | **₹0** |
| **Quant Tier** | Live agent deployment + live broker execution | Stripe (USD) · Razorpay (INR/UPI) |
| **Swarm Tax** | 1% monthly on copied capital, split 50/50 platform / strategy creator | Usage-based |

> Live deployment is gated behind an active Quant Tier subscription. Everything else — including the AI builder, the advisor, and the institutional backtester — is free, because you bring your own AI key and your own broker.

---

## 📁 Project Structure

```
AlphaSwarm/
├── app/
│   ├── api/           # auth, brokers (+OAuth), market, portfolio, notifications,
│   │                  # billing, backtest, llm_configs, ws, ai_advisor, social, social_feed
│   ├── core/          # config (pydantic-settings), celery_app, rate_limit, redis_pool
│   ├── db/            # asyncpg pool + JSONB codec, tenant-scoped repositories
│   ├── domain/        # base_strategy, risk (verify_order_intent), market_hours,
│   │                  # broker_routing, prompts, models
│   ├── services/      # strategy_builder & ai_advisor (Agent Framework), backtest,
│   │                  # execution, oauth_manager, billing, email, sms, broker_crypto,
│   │                  # sandbox, forecaster, forecasting (GBM), news_intel, indicators
│   ├── worker/        # celery tasks, beat_tasks (snapshots, OOS recompute), billing_tasks
│   └── main.py        # FastAPI app, lifespan, Sentry, health checks
├── alembic/versions/  # 0001 → 0014 (schema, OAuth/SIP, billing, unified holdings,
│                      # social copy trading, feed, broker login, email verify, OTP,
│                      # commons lineage, out-of-sample honesty)
├── frontend/src/app/  # Next.js 14 — dashboard, terminal, strategies, leaderboard,
│                      # advisor, portfolio, feed, settings, login (+ OTP / OAuth callbacks)
├── tests/             # 15 suites: risk, sandbox security, backtest metrics, billing,
│                      # broker crypto, BYOK founder gate, no-fund-custody, copy trading…
├── .github/workflows/ # CI: lint (ruff) + type-check + tests
├── docker-compose.yml · docker-compose.prod.yml · Dockerfile · nginx/
├── ARCHITECTURE.md · PROJECT_JOURNEY.md · schema.sql
```

---

## 🤝 Contributing

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) before writing code. Hard rules:

- **No LangChain** — Microsoft Agent Framework only.
- **No NSEpy** — yfinance / Upstox / Zerodha only.
- **No TA-Lib** — pandas-ta only.
- **`verify_order_intent()` before every broker call** — always, including backtests.
- **Every query filters `tenant_id`** — enforced in `BaseRepo`, never bypass it.

```bash
pytest            # tests
ruff check .      # lint
```

---

## 📜 License

MIT © 2026 AlphaSwarm — built by [Ankit Anand Singh](https://github.com/Algo-Ankit)

---

<div align="center">

**AlphaSwarm is being built in public.**
Star the repo to follow the journey from raw infrastructure to a full AI trading platform.

[![GitHub Stars](https://img.shields.io/github/stars/Algo-Ankit/AlphaSwarm?style=social)](https://github.com/Algo-Ankit/AlphaSwarm)

*The platform is live as an MVP — bring your key, bring your broker, and trade.*

</div>
