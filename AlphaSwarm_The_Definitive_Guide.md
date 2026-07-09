# AlphaSwarm — The Definitive Handbook

**Read this to understand the whole system, and to be able to teach or explain any part of it to someone else.**

This is not the marketing README (that's `README.md`). This is the *engineering study guide*: what each piece does, **how it actually works under the hood**, **why** it was built that way, and the finance/CS concepts you'd need to explain it in an interview, a pitch, or to a new engineer. Every claim here is traceable to real code — file paths are given so you can jump from a sentence to the source.

> **How to read this document**
> - Skim **§1–§3** for the mental model. If someone asks "what is this?", that's your answer.
> - **§5** are two end-to-end walkthroughs — read these to understand how data *flows*.
> - **§6** is the deep dive, one subsystem at a time. Each has the same shape: **The problem → How it works → The concept to teach → Where it lives.**
> - **§9** is a plain-English glossary of every finance/quant term. If a word is unfamiliar, it's defined there.
> - **§11** gives you three ready-made explanations (60 seconds / 5 minutes / whiteboard).

---

## Table of Contents

1. [The one-paragraph mental model](#1-the-one-paragraph-mental-model)
2. [The business thesis: why "no custody" is the entire strategy](#2-the-business-thesis-why-no-custody-is-the-entire-strategy)
3. [The stack at a glance — and why each piece](#3-the-stack-at-a-glance--and-why-each-piece)
4. [Architecture in four planes](#4-architecture-in-four-planes)
5. [Two end-to-end walkthroughs](#5-two-end-to-end-walkthroughs)
6. [Subsystem deep dives](#6-subsystem-deep-dives)
7. [Security architecture](#7-security-architecture)
8. [The data model & migration story](#8-the-data-model--migration-story)
9. [Finance & quant glossary](#9-finance--quant-glossary)
10. [Engineering decisions — the interview catalog](#10-engineering-decisions--the-interview-catalog)
11. [How to explain AlphaSwarm](#11-how-to-explain-alphaswarm)
12. [Battle scars — the bugs that shaped the system](#12-battle-scars--the-bugs-that-shaped-the-system)
13. [The codebase map](#13-the-codebase-map)

---

## 1. The one-paragraph mental model

**AlphaSwarm is an AI quant team that lives in a browser tab.** A user describes a trading strategy in plain English ("buy RELIANCE when RSI drops below 30"), and the AI writes validated Python for it, backtests that Python against realistic market conditions, and — once the user connects their *own* brokerage — trades it on their behalf. Around that core sit three products for three audiences: a **wealth copilot** for retail investors (goals, SIPs, an AI advisor), a **Bloomberg-style terminal** for active traders (candles, indicators, live P&L), and a **GitHub-style commons** for quants (fork, copy, and honestly-score each other's strategies). The one non-negotiable rule underneath all of it: **AlphaSwarm never touches the user's money.** Funds stay in the user's Zerodha/Upstox/Angel One/Alpaca account. The platform is software that *sends orders*, not a broker and not a fund. That single fact is the trust model and the business model at once.

If you remember nothing else, remember this: **"It's Bloomberg Terminal meets GitHub, running on your own broker and your own AI key, so we never custody money or bill you for tokens."**

---

## 2. The business thesis: why "no custody" is the entire strategy

Most people hear "trading platform" and assume the hard part is the trading. It isn't — the hard part is **regulation**. The moment a company holds customer funds or pools money into a fund, it needs money-transmitter / broker-dealer / investment-adviser licenses, custody insurance, audits, and capital reserves. That's a multi-year, multi-million-dollar moat *against you*, the founder.

AlphaSwarm sidesteps all of it with two "Bring Your Own" principles:

- **BYOB — Bring Your Own Broker.** The user connects their existing regulated brokerage. AlphaSwarm's servers send buy/sell *instructions* through that broker's API. The cash and the securities never leave the user's own account. Because we never hold money, we are a *software vendor*, not a financial institution. **This is why the company is fundable at the seed stage by one founder** — the regulatory overhead is near zero.

- **BYOK — Bring Your Own Key.** The AI features run on the *user's own* free LLM API key (Groq, Gemini, OpenRouter, or a local Ollama). AlphaSwarm ships no hidden paid key and never bills for tokens. This kills the single largest variable cost of an AI product (inference) and means the AI features can be **free forever**. Revenue comes from a subscription that gates *live deployment* and a usage fee on *copied capital* — never from AI usage.

**How to teach this:** "The genius isn't the AI — it's the org chart. By refusing to hold money and refusing to hold the AI key, AlphaSwarm turns the two most expensive, most regulated parts of a fintech into the user's problem, and keeps only the part that's pure software."

The revenue model that falls out of this:

| Tier | What it unlocks | How it's priced |
|------|-----------------|-----------------|
| **Free / BYOK** | AI builder & advisor, paper trading, full backtester, terminal, goal wizard, the Swarm | ₹0 |
| **Quant Tier** | Live agent deployment + live broker execution | Subscription (Stripe USD / Razorpay INR) |
| **Swarm Tax** | 1% per month on copied capital, split 50/50 platform ↔ strategy creator | Usage-based |

---

## 3. The stack at a glance — and why each piece

| Layer | Technology | The reason it was chosen (teach this) |
|-------|-----------|----------------------------------------|
| Frontend | **Next.js 14 (App Router)**, TypeScript, TailwindCSS | Server components + file-based routing; deploys free on Vercel. |
| Charts | **TradingView Lightweight Charts v4** + Chart.js | The only lib that renders ~10k candles + sub-charts at terminal speed. Chart.js for wealth-projection line charts. |
| Code editor | **Monaco** | The literal VS Code editor engine, in the browser — for quants who write Python directly. |
| API | **FastAPI** (Python 3.11) | Async-native, automatic OpenAPI docs, Pydantic validation at the edge. |
| DB driver | **asyncpg** (raw SQL, *no ORM*) | 3–5× faster on read-heavy paths; every query carries an explicit `tenant_id`, so isolation is visible, not hidden behind ORM magic. |
| Migrations | **Alembic** (async engine over asyncpg) | Version-controlled schema without needing the `psycopg2` C-compiler. |
| Database | **PostgreSQL 16** | Relational integrity + `pg_advisory_xact_lock` (the concurrency weapon, see §6.2) + JSONB. |
| Queue / cache / pub-sub | **Celery 5 + Redis 7** | Redis is the Celery broker *and* the WebSocket pub/sub bus. Kafka would be overkill — Redis is in-RAM and sub-millisecond. |
| AI orchestration | **Microsoft Agent Framework** (ReAct) | Stable API. LangChain is **banned** (breaks on minor upgrades); AutoGen was migrated *off* once it went maintenance-only. |
| AI model | **BYOK** — Groq / Gemini / OpenRouter / Ollama / Claude | User brings a free key. No shipped paid key, no token billing. |
| Technical analysis | **pandas-ta** | Pure Python — no TA-Lib C-compile pain across OSes. |
| Forecasting | **Prophet + statsmodels ARIMA** (ensemble) and **GBM Monte Carlo** | Price forecast with confidence bands; wealth projection over whole portfolios. |
| Sandbox | **RestrictedPython** | Safe execution of untrusted user-written strategy code. |
| Auth | **python-jose + passlib (bcrypt)** | RS256 JWT (HS256 dev fallback); Google + Upstox OAuth; stateless OTP & action tokens. |
| Market data | **Alpaca** (US/crypto), **yfinance** (`.NS`/`.BO` India), **Upstox/Zerodha** (live India) | `NSEpy` is permanently banned — it scrapes dead NSE endpoints. |
| Billing | **Stripe (USD)** + **Razorpay (INR/UPI)** | Dual gateway; gates live deployment only. |
| Ops | **Sentry, SendGrid, Twilio, GitHub Actions** | Errors, transactional email, SMS OTP, CI. All degrade to no-ops if unconfigured. |
| Infra | **Hetzner (~€15/mo) + Cloudflare + Vercel** | Production-grade at bootstrap pricing — not AWS at ~$250/mo for the same thing. |

---

## 4. Architecture in four planes

The system separates into four planes, each with a single responsibility. Understanding this split is understanding the system.

```
┌──────────────────────────────────────────────────────────┐
│  1. PRESENTATION  (Next.js 14 — Vercel)                   │
│  Dashboard · Terminal · Strategies · Leaderboard ·        │
│  Advisor · Portfolio · Feed · Settings · Login            │
└───────────────────────┬──────────────────────────────────┘
                        │  REST + WebSocket, JWT Bearer
┌───────────────────────▼──────────────────────────────────┐
│  2. CONTROL PLANE  (FastAPI + asyncpg)                    │
│  Validates, authorizes, reads/writes Postgres, enqueues   │
│  work. Holds NO trading loop itself — it's the front desk. │
└───────┬────────────────────────┬─────────────────────────┘
        │ Celery (Redis broker)  │ direct async service calls
┌───────▼────────────┐   ┌───────▼──────────────────────────┐
│  3. EXECUTION PLANE│   │  INTELLIGENCE SERVICES            │
│  (Celery workers)  │   │  market_data · indicators ·       │
│  Strategy loop ·   │   │  backtest · forecaster ·          │
│  Risk gate ·       │   │  news_intel · strategy_builder ·  │
│  Order execution · │   │  ai_advisor · oauth_manager       │
│  SIP · Swarm Tax · │   │                                   │
│  OOS recompute     │   │                                   │
└────────────────────┘   └───────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────┐
│  4. DATA PLANE                                            │
│  PostgreSQL 16 (source of truth) · Redis 7 (broker+pubsub)│
└──────────────────────────────────────────────────────────┘
```

**Why this split matters:** the FastAPI control plane is *stateless and fast* — it never runs a trading loop, so a slow strategy can never block a user's dashboard request. All the long-running, risky work (waiting for market bars, calling broker APIs) happens in **Celery workers** that are isolated per task queue. If a worker crashes mid-strategy, the API stays up and the database is still consistent. This is the classic **"web tier vs. worker tier"** separation, and it's the single most important structural decision in the codebase.

---

## 5. Two end-to-end walkthroughs

Reading data-flow beats reading feature lists. Here are the two flows that define the product.

### Walkthrough A — "Plain English → a live strategy"

1. **User types** *"Buy RELIANCE when RSI(14) < 30 and price > 200-day EMA; take profit 8%."* Frontend `POST`s it to the API with the user's JWT.
2. **Control plane** authenticates the JWT (extracts `user_id`, `tenant_id`, `role`), then calls `services/strategy_builder.py`.
3. **The AI agent** (Microsoft Agent Framework, ReAct pattern) turns the sentence into a Python `BaseStrategy` subclass. Crucially, it doesn't just emit text — it **calls a validation tool** that runs the code in the RestrictedPython sandbox (`services/strategy_sandbox.py`), sees the errors, and **fixes itself** in a loop. It runs on the user's BYOK model.
4. **Output contract:** a validated strategy + a plain-English explanation. If it can't produce valid code, it returns `{error, suggestion}` — it never silently emits broken code.
5. **User backtests it.** `services/backtest.py` replays historical OHLCV bars through the strategy. **The same `verify_order_intent()` risk function that governs live trading runs on every simulated order** (§6.2). Slippage, gap fills, and a volume-participation cap make the result honest (§6.5).
6. **User reviews metrics** — Sharpe, Sortino, max drawdown, etc. (all defined in §9) — and the equity curve overlaid on the chart.
7. **User connects a broker** and clicks Deploy. This requires an active **Quant Tier** subscription (the live gate). A Celery worker now runs the strategy loop: on each new bar it computes indicators, the strategy emits an intent, **the risk gate approves or rejects it**, and only approved intents become real broker API calls.

### Walkthrough B — "A creator's signal → 400 followers' brokers" (copy trading)

This is the fan-out that makes the Swarm work, and the part people most often get wrong.

1. A **creator** publishes a strategy to the commons. Publishing **pins an immutable version** (a frozen snapshot) and requires ≥ 3 on-platform backtests first (§6.7).
2. **Followers subscribe**, each allocating an amount of *their own* capital (say ₹50,000). No money moves to AlphaSwarm — the allocation is just a sizing number.
3. When the creator's strategy fires a buy signal, the execution engine **fans the signal out** to every subscriber. For each subscriber it: (a) takes a **per-subscriber advisory lock** so two signals can't double-fill the same account, (b) sizes the order to *that subscriber's* allocated capital, (c) runs **that subscriber's own risk gate**, and (d) sends the order through **that subscriber's own broker**.
4. The platform **never pools funds**. 400 followers = 400 independent orders in 400 independent brokerage accounts. The creator's account is untouched by the followers.
5. Monthly, the **Swarm Tax** task charges 1% of copied capital, split 50/50 between platform and creator (`worker/billing_tasks.py`).

**How to teach the difference from a hedge fund:** "A fund pools everyone's money into one account the manager controls. AlphaSwarm copies the *decision*, not the *money* — each follower's trade happens in their own account, sized to their own capital, gated by their own risk limits. That's why it needs no fund license."

---

## 6. Subsystem deep dives

Each subsystem below follows the same four beats: **the problem, how it works, the concept to teach, where it lives.**

### 6.1 Authentication & identity — five doors, one session

**The problem.** Traders arrive with different habits (email, Google, phone), and the founder needs to test as admin without being blocked by broker onboarding. Every path must land on the same secure session.

**How it works.** Five sign-in methods, all producing the same JWT session:

| Method | Mechanism |
|--------|-----------|
| Email + password | bcrypt-hashed password; email verification; refresh-token rotation. |
| Continue with Google | OIDC identity only (connects *no* brokerage); trusts Google's `email_verified` claim. |
| Email/phone OTP | One field accepts an email *or* a mobile number. A 6-digit code is sent (email via SendGrid, SMS via Twilio). Only `sha256(code)` is stored; the code is single-use, attempt-capped, and resend-throttled. In dev the code is logged to the console so you can sign in with no gateway. |
| Continue with Upstox | One click authenticates *and* connects the Indian brokerage for live execution — no API keys to copy/paste. |
| Broker API keys (Zerodha / Angel One / Alpaca) | For power users; keys are encrypted at rest (§7). |

Two token types worth understanding deeply:
- **Access + refresh tokens.** The **access token** is a short-lived (15-min) JWT carrying `user_id + tenant_id + role`. The **refresh token** is a 32-byte random secret, stored only as its SHA-256 hash, valid 30 days, and **rotated on every use** — if an old refresh token is replayed, reuse is detected and the family is invalidated.
- **Stateless action tokens.** Password-reset and email-verify links are *signed JWTs*, not database rows. The clever part: the reset token embeds a fingerprint (hash) of the *current* password. The moment the password changes, that fingerprint no longer matches, so the link **self-invalidates** — no "used tokens" table needed.

**The concept to teach.** *Stateless vs. stateful auth.* A stateful system stores every session/token in the DB and checks it on each request. AlphaSwarm keeps the hot path stateless (verify a signature, done) and only stores the *one* thing that must be revocable — the refresh token's hash. Action tokens go fully stateless by binding to data that already changes (the password hash).

**Where it lives.** `app/api/auth.py`, `app/services/auth.py`, `app/services/oauth_manager.py`, `app/services/email.py`, `app/services/sms.py`, `app/db/repositories/users.py`. Migrations `0010` (broker login), `0011` (email verification), `0012` (OTP).

---

### 6.2 The risk engine — the sacred wall

**The problem.** A trading bug can lose real money in milliseconds. There must be exactly **one** gate that every order passes through, in live trading *and* in backtests, with no second door.

**How it works.** `verify_order_intent()` in `app/domain/risk.py` is a **pure function** — no I/O, fully testable — that an order intent must pass before it can become a broker call. It runs a fixed sequence of checks and fails **closed** (rejects on any doubt):

1. **Market open?** — no orders outside the exchange's regular hours (skipped in backtests, where `market_state` is `None`).
2. **Paper-trading gate** — a paper-only strategy can't emit a live order.
3. **Symbol allowed** — the symbol must be on the strategy's allow-list.
4. **Whole-share enforcement** — Indian cash equity (NSE/BSE) rejects fractional shares, so the gate does too (US equity/crypto allow fractions — no-op there).
5. **Order notional ≤ strategy cap** — using a *gap-safe* price (see below).
6. **Per-symbol position cap** — the order can't push total exposure in one symbol past its limit (correctly handling stop-and-reverse overshoot).
7. **Max concurrent open positions** — opening a *new* position when already at the position-count limit is rejected.
8. **Daily executed notional ≤ daily cap** — only *exposure-increasing* notional counts; closing trades don't burn the daily budget.
9. **Platform-level cap** — a hard ceiling above the per-strategy cap, currency-converted.

The **gap-safety margin** is the subtle bit worth teaching: when there's no live tick, the daily/order caps don't trust yesterday's close blindly. A stock can gap up violently at the open and blow past a rupee cap while stale-price math still reads "under limit." So the gate sizes caps on the close *inflated by 3%* (`GAP_SAFETY_MARGIN`), guaranteeing it errs toward rejection on an open gap.

**The concurrency weapon.** In live trading two signals can arrive for the same account at once. Read-position → decide → place-order is a classic **TOCTOU** (time-of-check-to-time-of-use) race that can double-fill. The fix: a PostgreSQL **transactional 64-bit advisory lock** (`pg_advisory_xact_lock`) keyed to the account, with the position read done *inside* the same transaction. One signal waits for the other; no double-fills. (See `services/execution.py`.)

**The concept to teach.** *A single, un-bypassable choke point.* Security and safety come from having *one* place that enforces the rule, proven by tests, rather than sprinkling checks through strategy code where any one could be forgotten. "Adding a new risk rule means adding it here — never in strategy code."

**Where it lives.** `app/domain/risk.py` (the wall), `app/services/execution.py` (the lock + broker calls), `tests/test_risk.py`.

---

### 6.3 The AI strategy builder — natural language to deployable Python

**The problem.** A retail trader has intuition but can't code; a naive "ask an LLM for Python" approach hallucinates broken strategies that would fail at runtime — potentially with money on the line.

**How it works.** Built on the **Microsoft Agent Framework** using the **ReAct** pattern (Reason + Act). The agent doesn't emit code in one shot; it loops: reason about the request → write a candidate → **call the sandbox-validation tool** (real execution, real errors) → read the failure → fix → repeat, until the code is a valid `BaseStrategy` subclass. It runs entirely on the user's BYOK model.

**The concept to teach.** *Tool-grounded generation / self-correction.* The reason the output is trustworthy isn't that the model is smart — it's that the agent is **grounded in a real validator**. It can't declare success until actual execution passes. This is the difference between "an LLM wrote some code" and "an agent produced code that provably compiles and runs in our sandbox."

**Where it lives.** `app/services/strategy_builder.py`, `app/services/strategy_compiler.py`, `app/domain/base_strategy.py`, `app/domain/prompts/`.

---

### 6.4 The sandbox — running untrusted code safely

**The problem.** Users (and the AI) submit arbitrary Python. Run it naively and you have **remote code execution** and **denial-of-service** on your server.

**How it works.** `RestrictedPython` compiles user code with a restricted AST, then executes it with a locked-down set of builtins. Hardening added after a real security audit:
- **str-subclass guard** — blocks smuggling attacks that subclass `str` to bypass name checks.
- **`.format` denylist** — the `str.format` map-access trick can walk object internals; it's blocked.
- **`iter(int, sentinel)` DoS removed** — a two-arg `iter` that never terminates is disallowed.
- **`ReadOnlyDataFrame`** — market data handed to strategies can't be mutated to attack the engine.
- **Execution timeout** — a `SIGALRM`-based wall-clock cap (`services/exec_timeout.py`) kills infinite loops.

**The concept to teach.** *Defense in depth for untrusted code.* No single guard is trusted; you restrict the language (AST), restrict the environment (builtins), restrict the data (read-only frames), and bound the time (timeout). Each layer catches what the others miss.

**Where it lives.** `app/services/strategy_sandbox.py`, `app/services/exec_timeout.py`, `tests/test_sandbox_security.py`.

---

### 6.5 The institutional-grade backtester — an honest time machine

**The problem.** Most retail backtesters *lie*. They fill stop-losses at exactly the stop price (impossible when the market gaps through it), assume infinite liquidity (you can buy any size at the shown price), and ignore commissions and borrowing costs. The result is a beautiful equity curve that evaporates in live trading. That gap between backtest and reality is where retail traders lose money.

**How it works.** `services/backtest.py` replays historical OHLCV through `strategy.on_bar()` and models the frictions that make results honest:
- **Adverse gap fills.** If price gaps *past* a stop-loss overnight, the fill is at the adverse **open** price, not the (never-traded) stop price. Filling a gapped stop at the stop price is "hallucinated P&L — the market never traded there."
- **Volume-participation cap.** A single fill can absorb at most **10% of the bar's volume** (an Almgren–Chriss-style market-impact constraint). You can't buy a million shares in a thin stock at one price.
- **Bid/ask + slippage + commissions** are applied to every fill; profit factor and win rate are **commission-aware**.
- **Short-borrow financing** and terminal-liquidation costs are charged.
- **The risk gate runs on every simulated order** — the backtest and live trading share the exact same `verify_order_intent()` path, so a strategy can't behave differently in the two worlds.

The **metrics** it outputs (all defined in §9): Total Return, CAGR, Sharpe, **Sortino** (true RMS downside deviation, not a shortcut), Max Drawdown, Calmar, Win Rate, Profit Factor, plus alpha vs. a benchmark. Undefined ratios (e.g. Calmar with zero drawdown) use a `999.0` sentinel meaning "return with no downside," rather than crashing or dividing by zero.

**The concept to teach.** *Backtest realism / avoiding look-ahead and fantasy fills.* A backtest is only useful to the degree it refuses to let you cheat. Every friction added is a way of saying "the market would not actually have given you that."

**Where it lives.** `app/services/backtest.py`, `tests/test_backtest_metrics.py`.

---

### 6.6 Market data & indicators

**The problem.** Data comes from different venues in different shapes (US vs. India, live vs. historical), and indicators must be computed identically everywhere.

**How it works.** All prices are normalized to one canonical `Bar` model regardless of source (Alpaca for US/crypto, yfinance with `.NS`/`.BO` for Indian daily, Upstox/Zerodha for live India). Indicators (RSI, MACD, Bollinger, EMA, VWAP) are computed **server-side** with `pandas-ta`; the client only renders. Indicators are parameterizable at runtime — `rsi(21)`, `macd(5,35,5)`, `bb(20,2.5)`.

**The concept to teach.** *Canonical models + server-side computation.* By funneling every data source into one `Bar` type and computing indicators in one place, a strategy behaves identically no matter where its data came from, and the browser never disagrees with the backtester.

**Where it lives.** `app/services/market_data.py`, `app/services/indicators.py`, `app/domain/market_data.py`, `app/domain/market_hours.py`.

---

### 6.7 The Swarm — a strategy commons (GitHub for strategies)

**The problem.** Public strategy leaderboards rot into **survivorship-bias theater**: only winners get shown, overfit flukes look like skill, and "posts" get quietly edited after the fact so nobody can tell what was actually claimed. A commons is only trustworthy if lineage is provable and performance is honestly out-of-sample.

**How it works — four ideas, each a deliberate design decision:**

1. **Immutable published versions.** Publishing *pins* the exact `strategy_version` (already an immutable table). What people copy or fork is a **frozen snapshot**, never an editable post. You can't publish a loser and silently swap in a winner later.
2. **The fork graph.** Anyone can fork a listing into their own workspace (copying the pinned version). The system records `forked_from`, so the lineage — *"the strategy 400 people forked, and the mutations that beat the original"* — is a live, queryable graph (recursive CTE over ancestors and children).
3. **Anti-survivorship gates + out-of-sample scorecards.** Publishing requires **≥ 3 on-platform backtests** (`MIN_BACKTEST_RUNS_TO_PUBLISH`). Then a daily Celery task (`recompute_commons_oos`) backtests each listing's pinned version over data that only exists *after* its publish date and writes an **out-of-sample scorecard** (OOS return, Sharpe, drawdown…). Decayed alpha is shown, not hidden. **This is the honesty mechanism** — a strategy can't be tuned to its own test data because the test data didn't exist yet when it was published.
4. **Copy trading + the Swarm Tax.** Subscribers copy signals into their *own* accounts (see Walkthrough B); a 1%/month Swarm Tax on copied capital is split 50/50 platform ↔ creator.

**The concept to teach.** *Out-of-sample validation and provenance.* In-sample results (measured on the data you fit to) are almost meaningless — anything can be curve-fit. The only test that counts is performance on data the strategy never saw. Pinning immutable versions + scoring on post-publish data is how the commons makes that guarantee structurally, not by trusting anyone.

**Where it lives.** `app/api/social.py`, `app/db/repositories/social.py`, `app/worker/beat_tasks.py` (`recompute_commons_oos`), `app/worker/billing_tasks.py` (Swarm Tax). Migrations `0007` (copy trading), `0013` (lineage), `0014` (OOS).

---

### 6.8 The AI investment advisor + retrieval on the commons

**The problem.** A generic LLM advisor gives generic advice. It should reason from strategies that have actually been backtested on the platform.

**How it works.** A conversational advisor (rendered as sanitized markdown) for stock/ETF analysis and SIP/SWP planning, under the same strict BYOK enforcement as the builder. Its distinguishing feature is **retrieval-augmented grounding**: when a user describes a thesis, `ai_advisor._retrieve_commons_context` tokenizes the query (tickers weighted 2×, stopwords removed), ranks published commons strategies by token overlap, and injects the top matches as **few-shot context**. So **every strategy published to the commons makes the advisor smarter.** The advisor also powers the holdings risk narrative (§6.9).

**The concept to teach.** *RAG (retrieval-augmented generation).* Instead of relying on the model's frozen training data, you retrieve relevant, current, domain-specific documents at query time and put them in the prompt. Here the "documents" are the platform's own honestly-scored strategies — a data moat that compounds as the commons grows.

**Where it lives.** `app/services/ai_advisor.py`, `app/api/ai_advisor.py`.

---

### 6.9 Portfolio & wealth-tech — for investors, not just traders

**The problem.** A trader wants P&L; an *investor* wants goals, diversification, and "what should I sell?" Different questions, different UI, different math.

**How it works — four capabilities:**

- **Unified multi-broker holdings.** Import a Consolidated Account Statement (CAS) from NSDL/CDSL and see holdings across brokers in one view (`portfolio_parser.py`, migration `0006`).
- **XIRR** — the true money-weighted return across irregular cash flows (SIPs go in monthly, at different prices), solved with Newton–Raphson. A plain "return %" is wrong when contributions are staggered; XIRR is the honest number (§9).
- **Deterministic risk review + optional AI narrative.** `services/portfolio_risk.py` is a **pure, LLM-free** engine that scores each holding **Trim / Review / Hold** from concentration (per-holding weight + a Herfindahl–Hirschman **HHI** index), drawdown, and broker/asset-class concentration. It always runs, with no AI key. When the user opts in *and* has a BYOK key, `ai_advisor.review_holdings` layers a plain-English narrative on top — best-effort, never blocking the scorecard. Endpoint: `GET /portfolio/risk-review?include_ai=`.
- **Monte Carlo wealth forecast.** A **Geometric Brownian Motion** simulation (`services/forecasting.py`) projects portfolio value years out as P10 / P50 / P90 bands — "pessimistic / median / optimistic" — instead of a single fake number.

**The concept to teach.** *Deterministic core, AI as a layer.* The risk scorecard is defensible math that works offline and can't hallucinate. AI is the *explanation* on top, never the source of truth. This is the right pattern for any AI feature where being wrong has consequences: compute the answer deterministically, use the model only to narrate it.

**Where it lives.** `app/api/portfolio.py`, `app/services/portfolio_risk.py`, `app/services/portfolio_parser.py`, `app/services/forecasting.py`, `app/db/repositories/unified_holdings.py`.

---

### 6.10 Realtime — WebSockets over Redis pub/sub

**The problem.** A terminal must show live bars, live P&L, and notifications without the browser polling every second.

**How it works.** Celery workers publish updates to Redis channels; the FastAPI WebSocket endpoint (`app/api/ws.py`) subscribes and fans them out to connected browsers over `/v1/ws/portfolio` and the bars channel. The Redis client is **async** so publishing never blocks the ASGI event loop (this was a real bug once — a sync `.publish()` stalled the whole server; see §12).

**The concept to teach.** *Pub/sub decoupling.* The worker that computes a P&L update doesn't know or care who's watching. It publishes to a channel; the web tier handles delivery. This decouples producers from consumers and lets either scale independently.

**Where it lives.** `app/api/ws.py`, `app/core/redis_pool.py`, `app/worker/beat_tasks.py` (snapshots).

---

### 6.11 Billing — one product, two gateways

**The problem.** US customers pay by card (Stripe); Indian customers pay by UPI/netbanking (Razorpay). The rest of the app shouldn't care which.

**How it works.** A currency (`USD`→Stripe, `INR`→Razorpay) selects the gateway; both return a `{gateway, checkout_url, reference_id}`. Webhooks are **signature-verified** before any subscription state changes — a hard lesson from a "phantom revenue" bug where unverified webhooks could fake a paid subscription (§12). Subscription state gates **live deployment** only; everything else is free.

**Where it lives.** `app/api/billing.py`, `app/services/billing.py`, `app/worker/billing_tasks.py`. Migrations `0003`–`0005`, `0008`, `0009`.

---

## 7. Security architecture

Read this as a checklist you can defend line by line:

```
Access token   RS256 JWT · 15-min expiry · sub = user_id + tenant_id + role  (HS256 dev fallback)
Refresh token  32-byte random · SHA-256 hashed in DB · 30-day · rotated on use, reuse-detected
Action tokens  stateless signed JWTs for password reset / email verify — reset embeds a hash of
               the current password, so the link self-invalidates the instant the password changes
Login OTPs     only sha256(code) stored · single-use · attempt-capped · resend-throttled
Multi-tenancy  every query carries WHERE tenant_id = $N · enforced in BaseRepo, impossible to skip
Broker keys    HKDF + Fernet envelope encryption at rest · decrypted in memory only
OAuth          signed-token CSRF on every flow · Indian broker tokens auto-refresh via retry_on_401
Code sandbox   RestrictedPython · str-subclass guard · format denylist · iter DoS removed · exec timeout
LLM access     strict BYOK · founder-only platform-key fallback gated by a timing-safe email compare
```

Two ideas worth being able to explain:
- **Envelope encryption (broker keys).** Rather than encrypting every broker secret directly with one master key, a per-secret data key is derived (HKDF) and the payload sealed with Fernet. Compromising one ciphertext doesn't hand over everything, and keys live decrypted only in memory during a request.
- **Tenant isolation in `BaseRepo`.** Every repository method carries `WHERE tenant_id = $N`. Because it's enforced in the shared base class (not per-query by hand), one tenant can *never* read another's rows — the isolation is structural, not disciplinary.

**Where it lives.** `app/services/broker_crypto.py`, `app/db/repositories/` (BaseRepo), `app/services/auth.py`. Tests: `test_broker_crypto.py`, `test_byok_founder_gate.py`, `test_no_fund_custody.py`.

---

## 8. The data model & migration story

The schema is version-controlled as Alembic migrations `0001 → 0014`. Reading them in order is a compressed history of the product:

| Migration | What it added | Product moment |
|-----------|---------------|----------------|
| 0001 | Core schema — tenants, users, strategies, runs, positions | The foundation + multi-tenant isolation |
| 0002 | OAuth + SIP mandates | Broker connections + goal-based investing |
| 0003–0005 | Billing (Stripe, then Razorpay, then dual-gateway) | Monetization |
| 0006 | Unified holdings | Multi-broker CAS ingestion |
| 0007 | Public strategies + subscriptions | Social copy trading |
| 0008 | Social posts + creator balances + fee columns | The feed + Swarm Tax |
| 0009 | Feed likes + invoiced fee | Feed polish |
| 0010 | Broker-identity login | "Continue with Upstox" |
| 0011 | `users.email_verified` | Email verification |
| 0012 | `users.phone` + `login_otps` | Passwordless OTP login |
| 0013 | `published_version_id`, `forked_from`, `fork_count` | Immutable versions + fork graph |
| 0014 | `oos_*` columns | Out-of-sample honesty |

**The concept to teach.** *Migrations as an append-only history.* You never edit the schema by hand — each change is a numbered, reversible migration, so any environment can be rebuilt to any point by replaying them (`alembic upgrade head`).

---

## 9. Finance & quant glossary

The terms you need to *teach* the system. Each is one sentence you could say out loud.

**BYOB / BYOK** — Bring Your Own Broker / Bring Your Own Key: the user supplies the brokerage account and the AI API key, so the platform holds neither money nor inference cost.

**Notional** — the total cash value of an order or position (quantity × price). Risk limits are expressed in notional.

**Slippage** — the difference between the price you expected and the price you actually got; real markets move between decision and fill.

**Market impact / volume-participation cap** — your own order moves the price against you; you can't buy unlimited size at one price, so a fill is capped at ~10% of the bar's volume (Almgren–Chriss).

**Gap fill** — when a market opens far from the prior close, an order (like a stop-loss) fills at the gapped open, not the price it "should" have.

**RSI (Relative Strength Index)** — a 0–100 momentum oscillator; < 30 is often read as oversold, > 70 as overbought.

**MACD** — trend/momentum indicator from the difference of two EMAs and a signal line.

**Bollinger Bands** — a moving average plus/minus a volatility band; price at the edges signals stretch.

**EMA / VWAP** — Exponential Moving Average (recent-weighted trend line) / Volume-Weighted Average Price (the day's average price weighted by volume).

**Total return** — the overall percentage gain/loss over the period.

**CAGR** — Compound Annual Growth Rate: the smooth annual rate that would take you from start to end value; makes different time spans comparable.

**Sharpe ratio** — return per unit of *total* volatility; higher = better risk-adjusted return.

**Sortino ratio** — like Sharpe but penalizes only *downside* volatility (RMS of negative returns) — upside swings shouldn't count as "risk."

**Max drawdown** — the largest peak-to-trough drop in the equity curve; the worst pain an investor would have felt.

**Calmar ratio** — CAGR divided by max drawdown; return relative to worst-case pain.

**Profit factor** — gross profit ÷ gross loss; > 1 means the wins outweigh the losses.

**Win rate** — the fraction of trades that were profitable (necessary but not sufficient — a high win rate with huge losers still loses).

**Alpha** — return above a benchmark; the part attributable to the strategy rather than the market.

**Equity curve** — the running value of the account over time; the single most informative backtest chart.

**In-sample vs. out-of-sample** — measured on the data you fit to (nearly worthless — easy to curve-fit) vs. on data the strategy never saw (the only test that counts).

**Survivorship bias** — judging from only the survivors (winning strategies), which massively overstates expected performance.

**XIRR** — the money-weighted internal rate of return across irregular cash flows (like monthly SIPs at different prices); solved numerically (Newton–Raphson). The honest "what did I actually earn?" when contributions are staggered.

**HHI (Herfindahl–Hirschman Index)** — sum of squared weights; a concentration measure — one holding at 100% gives 1.0 (dangerously concentrated), many equal holdings approach 0 (diversified).

**SIP / SWP** — Systematic Investment Plan (invest a fixed amount on a schedule) / Systematic Withdrawal Plan (the reverse, in retirement).

**Monte Carlo / GBM** — running thousands of simulated future price paths (Geometric Brownian Motion) to get a *distribution* of outcomes (P10/P50/P90) instead of one false point estimate.

**Paper trading** — trading with fake money against real prices; the safe way to validate before going live.

---

## 10. Engineering decisions — the interview catalog

The non-obvious calls, phrased as the question you'll be asked and the answer you give.

**"Why no ORM?"** — Raw asyncpg is 3–5× faster on read-heavy paths, and it makes tenant isolation *visible* — every query literally says `WHERE tenant_id = $N`. ORMs hide that behind session magic where it's easy to leak across tenants.

**"Why Microsoft Agent Framework over LangChain?"** — LangChain ships breaking changes in minor versions, which is unacceptable in a system that places real orders. We even migrated *off* AutoGen when it went maintenance-only. Stability > features for infrastructure.

**"Why not TA-Lib for indicators?"** — TA-Lib needs a C compiler that breaks CI across OSes. pandas-ta is pure Python and installs in seconds.

**"Why yfinance and not NSEpy for Indian data?"** — NSEpy scrapes NSE endpoints that are chronically broken. It's permanently banned; yfinance with `.NS`/`.BO` suffixes is robust.

**"Why TradingView charts and not Recharts/Chart.js for candles?"** — It's the only library that renders ~10k candles plus sub-charts at terminal speed. Chart.js is fine for simple wealth-projection lines, which is where we still use it.

**"How do you prevent double-fills under concurrency?"** — A PostgreSQL transactional advisory lock (`pg_advisory_xact_lock`) per account, with the position read *inside* the transaction — closing the TOCTOU window.

**"How is a backtest honest?"** — Shared risk gate with live trading, adverse gap fills, a 10% volume-participation cap, commissions, and short-borrow costs. The backtest is engineered to refuse to let you cheat.

**"Why immutable versions in the commons?"** — Lineage is the value of a commons. If posts were editable, someone could publish a loser and swap in a winner. Pinning a frozen version + scoring it out-of-sample makes performance claims structurally honest.

**"Why deterministic risk scoring with AI on top, instead of just asking the LLM?"** — Because being wrong costs money. The math (weights, HHI, drawdown) is defensible and runs offline; the AI only narrates it. Never let the model be the source of truth for a consequential number.

**"Why Hetzner, not AWS?"** — ~€15/mo vs ~$250/mo for the same capability. At bootstrap stage, Docker Compose on a Hetzner box with Cloudflare + Vercel is production-grade and DevOps-light. Kubernetes would be premature.

**"Is Docker Compose production-grade?"** — For a seed-stage startup, yes: `docker-compose.prod.yml` mounts persistent volumes, scales workers (`--scale worker=N`), and delegates SSL/load-balancing to Nginx. K8s is for a later scale problem we don't have yet.

---

## 11. How to explain AlphaSwarm

Three scripts, for three situations.

### The 60-second version (an investor at a party)
> "AlphaSwarm is an AI quant team in a browser tab. You describe a trading strategy in plain English, the AI writes and honestly backtests the code, and it trades it through *your own* brokerage — we never touch your money. Around that we built a wealth copilot for regular investors, a pro terminal for active traders, and a GitHub-style commons where people fork and copy each other's strategies. Because we hold neither the money nor the AI key, the whole thing is fundable by one person and free at the base tier — we only charge to go live and take a small cut of copied capital."

### The 5-minute version (a technical hire)
Walk the four planes (§4): a stateless Next.js frontend, a fast FastAPI control plane that never runs a trading loop, isolated Celery workers that do, and Postgres+Redis underneath. Then the two flows in §5: NL → validated Python → honest backtest → gated live deployment; and a creator's signal fanning out to hundreds of *independent* broker accounts. Land on the three pillars: **the un-bypassable risk gate** (§6.2), **the honest backtester** (§6.5), and **the out-of-sample commons** (§6.7).

### The whiteboard version (a systems interview)
Draw the four planes. Emphasize the web-tier/worker-tier split and *why* (a slow strategy can't block a dashboard request). Then draw the order path: intent → `verify_order_intent()` (single choke point, fails closed) → advisory-lock'd execution → broker. Explain the TOCTOU race and the `pg_advisory_xact_lock` fix. Finish with tenant isolation in `BaseRepo` and BYOB/BYOK as the regulatory + cost moat.

---

## 12. Battle scars — the bugs that shaped the system

The git history reads like a postmortem. The ones worth telling as stories:

| Area | The bug | The fix (and the lesson) |
|------|---------|--------------------------|
| Persistence | Strategies lived in an in-memory dict — lost on every restart | Moved to Postgres via tenant-scoped repositories. *State belongs in the database.* |
| Concurrency | **TOCTOU double-fills** under concurrent signals | `pg_advisory_xact_lock` with the position read inside the transaction. *Check and act atomically.* |
| Security | **Sandbox RCE/DoS** via `str` subclassing, non-terminating `iter`, `.format` map access | Guarded getattr, type checks, format denylist, `ReadOnlyDataFrame`, exec timeout. *Defense in depth for untrusted code.* |
| Realtime | A sync Redis `.publish()` blocked the ASGI event loop; a WS race overwrote live data | Async Redis client; merge-not-replace state. *Never do sync I/O on the event loop.* |
| Backtester | Filled gapped stop-losses at the stop price (fantasy P&L) | Adverse-gap fills + volume cap + cost realism. *A backtest must refuse to cheat.* |
| Metrics | `OverflowError` on short-window CAGR; a wrong Sortino formula | Edge-case-hardened metrics, true RMS downside deviation. *Financial math has landmines at the boundaries.* |
| Billing | Phantom revenue from unverified webhooks; a Razorpay race | Signature-gated, idempotent subscription state. *Trust no webhook you haven't verified.* |
| Data model | Schema could orphan active SIPs (`ON DELETE SET NULL`) | `tenant_id` on mandates + strict `CHECK` constraints. *Let the database enforce invariants.* |

---

## 13. The codebase map

```
AlphaSwarm/
├── app/
│   ├── api/           # HTTP surface: auth, brokers(+OAuth), market, portfolio, notifications,
│   │                  #   billing, backtest, llm_configs, ws, ai_advisor, social, social_feed
│   ├── core/          # config (pydantic-settings), celery_app, rate_limit, redis_pool
│   ├── db/            # asyncpg pool + JSONB codec; tenant-scoped repositories (BaseRepo)
│   ├── domain/        # base_strategy, risk (verify_order_intent), market_hours,
│   │                  #   broker_routing, prompts, models   ← the pure business core
│   ├── services/      # strategy_builder & ai_advisor (Agent Framework), backtest, execution,
│   │                  #   oauth_manager, billing, email, sms, broker_crypto, strategy_sandbox,
│   │                  #   forecaster, forecasting (GBM), news_intel, indicators, portfolio_*
│   ├── worker/        # celery tasks, beat_tasks (snapshots, OOS recompute), billing_tasks
│   └── main.py        # FastAPI app, lifespan, Sentry, health checks
├── alembic/versions/  # 0001 → 0014 (see §8)
├── frontend/src/app/  # Next.js 14: dashboard, terminal, strategies, leaderboard, advisor,
│                      #   portfolio, feed, settings, login (+ OTP / OAuth callbacks)
├── tests/             # 15 suites: risk, sandbox security, backtest metrics, billing,
│                      #   broker crypto, BYOK founder gate, no-fund-custody, copy trading…
├── .github/workflows/ # CI: ruff lint + type-check + tests
├── docker-compose.yml · docker-compose.prod.yml · Dockerfile · nginx/
└── README.md · ARCHITECTURE.md · PROJECT_JOURNEY.md · this file
```

**The reading order for a new engineer:** `README.md` (the pitch) → this handbook (the mental model) → `app/domain/` (the pure core: `risk.py`, `base_strategy.py`) → `app/services/execution.py` and `backtest.py` (where the core meets the world) → then follow a request from `app/api/` down. `ARCHITECTURE.md` is the full 1000-line design spec — read it surgically, not front-to-back.

---

*This handbook tracks the platform as of the Strategy Commons phase (migrations through 0014). When a subsystem changes materially, update the relevant §6 section and, if it's a schema change, the §8 table. Keep it honest — the whole point of this document is that someone can trust it enough to teach from it.*

— Maintained alongside AlphaSwarm by [Ankit Anand Singh](https://github.com/Algo-Ankit)
