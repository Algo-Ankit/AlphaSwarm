# AlphaSwarm — Master System Design & Architecture
**Version 2.0 — Fully Resolved. All prior gaps addressed.**

> **MANDATORY FOR ALL AGENTS (Claude, Codex, Agy, or any future AI):**
> Read this ENTIRE file before writing a single line of code or running any command.
> When you complete a phase milestone, update the `CURRENT STATE & ROADMAP` section.
> The `.env.example` file documents every required environment variable.
> The `docker-compose.yml` file runs the full local infrastructure.

---

## 1. Product Vision

AlphaSwarm is a **production-grade, multi-tenant algorithmic trading SaaS** built to be a fundable startup MVP. Two types of users are served simultaneously:

1. **Retail Traders (Non-Coders)** — Describe a strategy in plain English. AI generates, validates, backtests, and deploys it. They monitor via a full trading terminal with candlestick charts, indicators, forecasting, and company news.
2. **Quant Developers** — Write Python strategies directly in a browser code editor. Deploy as isolated workers. Get the same professional terminal and infrastructure without building it themselves.

### North Star
> Bloomberg Terminal meets Linear. Every pixel earns its place. Every chart answers a question the trader is actually asking. No AI slop, no decoration, no filler.

---

## 2. User Personas

### Persona A — Retail Trader
- Has trading intuition, cannot code
- Monitors via charts + indicators, needs news context
- Needs confidence before going live → backtesting is mandatory
- Journey: Describe → AI generates + explains → Backtest → Review metrics → Deploy paper → Deploy live

### Persona B — Quant Developer
- Writes Python, understands TA algorithms
- Wants deployment infrastructure, not to build it
- Journey: Write Python class → Submit via Monaco editor → Sandbox validates → Backtest → Deploy

---

## 3. Technology Stack

### Backend
| Layer | Technology | Why |
|---|---|---|
| Control Plane | FastAPI + asyncpg | Async-first. Blocking DB calls kill throughput under concurrent trading load. |
| Database | PostgreSQL 16 | ACID correctness for financial data. JSONB for flexible configs. |
| Migrations | Alembic | Version-controlled schema changes. Never hand-edit production DB. |
| Task Broker | Celery 5 + Redis 7 | Isolated parallel workers per strategy. Battle-tested at scale. |
| Periodic Tasks | Celery Beat | News refresh, forecast regeneration, portfolio snapshots. Built into Celery. |
| Agent Framework | **Microsoft AutoGen (pyautogen)** | NOT LangChain. AutoGen is stable, multi-agent native, production-used at Microsoft. LangChain has constant breaking changes causing runtime failures. |
| AI Model | Claude Sonnet 4.6 (Anthropic API) | NL → strategy code generation, news sentiment, market analysis. |
| Technical Analysis | pandas-ta | Pure Python. No TA-Lib compile failures on any OS. |
| Forecasting | Prophet + statsmodels ARIMA | Prophet for daily/weekly seasonality. ARIMA for intraday. Both output confidence intervals. |
| News | NewsAPI + Alpha Vantage News | Two independent sources. Sentiment scored by Claude Haiku (fast + cheap). |
| Broker | Alpaca (paper + live) | Unified broker + US data API. Free paper trading account. |
| Code Sandbox | RestrictedPython | Safe execution of user-submitted strategy code. No network/filesystem/subprocess access. |
| Auth | python-jose (JWT) + passlib (bcrypt) | Stateless JWT access tokens + refresh token rotation. |
| Encryption | cryptography (Fernet) | Broker API keys stored encrypted at rest in DB. Never plaintext. |
| HTTP Client | httpx | Async HTTP for all external API calls. |
| Rate Limiting | slowapi | Per-endpoint, per-user rate limiting on FastAPI. |
| Error Tracking | Sentry (sentry-sdk[fastapi]) | Production error monitoring. |

### Market Data Sources
| Market | Primary | Fallback | Notes |
|---|---|---|---|
| US (NASDAQ, NYSE) | Alpaca Data API | yfinance | Alpaca is free with broker account and gives consistent format. |
| Indian EOD (NSE, BSE) | yfinance (`RELIANCE.NS`, `RELIANCE.BO`) | None | yfinance works for daily/weekly Indian data. |
| Indian Intraday (NSE) | Zerodha Kite Connect API | Angel One Smart API | Requires user's own broker API credentials. Configured in `/settings`. |
| Crypto | Alpaca Crypto | yfinance | |
| Global (other) | yfinance | None | |
| **IMPORTANT** | NSEpy is DEPRECATED and BROKEN | Do NOT use it | NSEpy fails on current NSE infrastructure. Use yfinance for Indian data. |

### Frontend
| Layer | Technology | Why |
|---|---|---|
| Framework | Next.js 14 App Router | SSR + RSC for performance. |
| Charts | **TradingView Lightweight Charts v4** | The ONLY library with production-grade candlestick + indicator support. Recharts, Chart.js, Victory — none are sufficient for a trading terminal. |
| State | Zustand | Lightweight global state. No Redux boilerplate. |
| Styling | TailwindCSS | Utility-first. |
| Real-time | Native WebSocket | Live ticks, live P&L. Full spec in Section 11. |
| Code Editor | Monaco Editor (@monaco-editor/react) | VS Code engine. Required for developer strategy path. |

---

## 4. Core Feature Modules

### Module 1 — Trading Terminal (`/terminal/[symbol]` and `/strategies/[id]`)
The primary product screen. Every element is functional.

**Chart Area (top 65% of screen):**
- Candlestick chart (OHLCV) via TradingView Lightweight Charts
- Timeframe selector: `1m / 5m / 15m / 1h / 4h / 1D / 1W`
- Indicator overlays on the price series: 20 EMA, 50 EMA, 200 EMA, Bollinger Bands, VWAP
- Sub-charts pane below main chart: RSI(14), MACD histogram + signal, Volume bars
- Indicator parameters are user-configurable: `rsi(21)`, `macd(5,35,5)`, `bb(20,2.5)`
- All indicator values computed server-side via pandas-ta. Client displays only.
- Market hours indicator: colored badge showing OPEN / PRE-MARKET / CLOSED / AFTER-HOURS

**Tabs (bottom 35% of screen):**
1. **Forecast** — 5-day Prophet + ARIMA ensemble. Shows: historical actuals, forecast line, 80% confidence band. Always labeled: *"Statistical projection — not financial advice."* Includes model error metrics (MAE, MAPE) for transparency.
2. **News** — Company-specific news, last 7 days. Per item: headline, source, published time, sentiment badge (Positive/Negative/Neutral), category badge (Earnings/Regulatory/Political/Product/Macro). Sorted by estimated price impact.
3. **Orders** — All orders from this strategy: symbol, side, qty, fill price, P&L per trade, timestamp.
4. **Performance** — Sharpe ratio, Sortino ratio, max drawdown, win rate, profit factor, avg trade duration, total trades, total return %. Computed from orders + positions tables.
5. **AI Analysis** — On-demand 2–3 sentence commentary from `AnalysisAgent` using current indicator snapshot + recent news headlines. Labeled as AI-generated opinion.

### Module 2 — Dashboard (`/dashboard`)
Portfolio-level view with real data only.

- **Stats row**: Total Portfolio Equity, Today's P&L (abs + %), Active Bots count, Portfolio Win Rate
- **Equity Curve**: Cumulative portfolio value over time. Data source: `portfolio_snapshots` table (written by Celery Beat every 5 minutes while any bot is live). X-axis: time. Y-axis: total equity in USD/INR.
- **Active Bots Grid**: Card per running strategy. Status dot (LIVE/PAUSED/ERROR), name, ticker badge, today's P&L, trade count, Stop/Resume action.
- **Recent Trades Feed**: Last 10 trades across all strategies. BUY/SELL badge, ticker, qty, price, P&L, timestamp.
- **Notification Bell**: Unread count badge. Opens notification panel.

### Module 3 — Strategy Builder (`/strategies/new`)
Two clearly separated paths. Same underlying engine.

#### Path A — No-Code (Natural Language)
1. User types: *"Buy RELIANCE when RSI(14) drops below 30 and close is above 200-day EMA. Sell when RSI crosses above 70. Max 1 lot."*
2. `StrategyBuilderAgent` (AutoGen + Claude Sonnet) interprets → generates a `BaseStrategy` Python subclass
3. User sees **plain-English confirmation** only. Code hidden unless "Show Code" toggle is clicked.
4. User configures: risk params, timeframe, exchange, paper/live toggle
5. User clicks **Backtest First** → runs `BacktestRunner` on last 6 months of data → shows performance metrics
6. If metrics acceptable: user clicks **Deploy** → Celery worker spawned

#### Path B — Developer Code Editor
1. Developer opens `/strategies/new?mode=code`
2. Monaco editor pre-loaded with `BaseStrategy` template + full docstring for `on_bar()`
3. Autocomplete for: `self.bars`, `self.indicators`, `self.place_order()`, `self.risk`, `self.position`
4. Submit → `RestrictedPython` sandbox validates + lints → syntax errors shown inline
5. Backtest → Deploy (same flow as Path A from step 5)

### Module 4 — Backtesting Engine
Built on top of the same `BaseStrategy` interface used for live trading.

- Input: strategy code + symbol + timeframe + date range + initial capital
- Data: fetched from `market_data_cache` or live from yfinance/Alpaca if not cached
- Engine: `BacktestRunner` replays historical bars through `strategy.on_bar()` sequentially
- Risk: same `verify_order_intent()` function called during backtest (no bypass)
- Output stored in `backtest_results` table:
  - Total return %, Sharpe ratio, Sortino ratio, Max drawdown %
  - Win rate, Profit factor, Total trades, Avg trade duration
  - Full trade log (JSON array of simulated fills)
- UI: performance metrics card + simulated equity curve on the same TradingView chart (separate series)

### Module 5 — Market Intelligence (`/market/[symbol]`)
Available for any ticker globally. Also embedded in terminal.

- Ticker search with exchange-aware autocomplete (sees NSE/BSE/NASDAQ/NYSE symbols)
- Symbol format resolver: user types `RELIANCE` → resolves to `RELIANCE.NS` for NSE
- Full terminal chart for that ticker (no strategy overlay)
- Forecast + News tabs
- No strategy/orders/performance tabs (those require a running strategy)

### Module 6 — Risk System
Non-negotiable. Every order passes through this before touching any broker API.

Checks performed (in order):
1. Market is currently open for this symbol's exchange (market hours check)
2. Symbol is on the allowed list for this strategy
3. Order notional ≤ strategy `max_order_notional`
4. Today's executed notional for this strategy ≤ `max_daily_notional`
5. Total open position value across all strategies for this tenant ≤ tenant plan limit
6. Paper trading gate (if `paper_trading_only: true`, reject live orders)

`verify_order_intent()` is the single entry point. It must never be bypassed. Adding a new check means adding it here, not in individual strategy code.

### Module 7 — Notification System
Real-time in-app notifications. Email in Phase 7.

Triggered by:
- Order executed (any strategy)
- Bot error (worker exception)
- Bot stopped (user-triggered or risk rejection)
- Daily P&L threshold crossed (configurable, e.g., -5% daily)
- News item published for a watched ticker
- Backtest complete

Stored in `notifications` table. Read via REST (`GET /v1/notifications`) and real-time via WebSocket push on the `/v1/ws/portfolio` channel.

---

## 5. System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (Next.js 14 App Router)                                   │
│                                                                       │
│  /dashboard            Portfolio + equity curve + bot grid           │
│  /terminal/[symbol]    Candlestick + TA + Forecast + News + AI       │
│  /strategies/new       Dual-pathway builder (NL or Code)             │
│  /strategies/[id]      Bot detail + performance + backtest           │
│  /market/[symbol]      Standalone market intelligence                │
│  /settings             Broker keys, alerts, plan                     │
│  /auth/login           JWT login                                     │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  REST (JSON) + WebSocket
                           │  Authorization: Bearer <JWT>
┌──────────────────────────▼───────────────────────────────────────────┐
│  CONTROL PLANE  (FastAPI + asyncpg)                                  │
│                                                                       │
│  Auth:     POST /v1/auth/login  POST /v1/auth/refresh                │
│  Strategy: CRUD + run dispatch + version management                  │
│  Market:   /v1/market/bars  /indicators  /forecast  /news            │
│  Portfolio:/v1/portfolio/equity-curve  /positions  /performance      │
│  Backtest: POST /v1/strategies/{id}/backtest                         │
│  Notify:   GET /v1/notifications  PATCH /v1/notifications/{id}/read  │
│  WebSocket:/v1/ws/bars/{symbol}  /v1/ws/portfolio  /v1/ws/run/{id}  │
└──────┬────────────────────────────────┬─────────────────────────────┘
       │ Celery tasks (Redis broker)    │ Direct async service calls
┌──────▼──────────────────┐   ┌─────────▼───────────────────────────┐
│  EXECUTION PLANE         │   │  INTELLIGENCE SERVICES               │
│  (Celery workers)        │   │                                      │
│                          │   │  market_data.py                      │
│  One isolated worker     │   │    Alpaca Data (US) / yfinance       │
│  per strategy run.       │   │    → canonical Bar model             │
│  Crash in one = no       │   │    → market_data_cache table         │
│  effect on others.       │   │                                      │
│                          │   │  indicators.py                       │
│  AutoGen agents:         │   │    pandas-ta: RSI, MACD, BB,         │
│  ┌────────────────────┐  │   │    EMA(n), VWAP, Stoch, ATR         │
│  │StrategyRunAgent    │  │   │    Parameterized: rsi(21), bb(20,2) │
│  │ reads bars,        │  │   │                                      │
│  │ calls on_bar(),    │  │   │  forecaster.py                       │
│  │ generates signals  │  │   │    Prophet + ARIMA ensemble          │
│  └────────────────────┘  │   │    Cached in forecasts table         │
│  ┌────────────────────┐  │   │    Regenerated by Beat if stale      │
│  │RiskAgent           │  │   │                                      │
│  │ pure function,     │  │   │  news_intel.py                       │
│  │ not LLM-based,     │  │   │    NewsAPI + Alpha Vantage           │
│  │ <1ms latency       │  │   │    Sentiment: Claude Haiku           │
│  └────────────────────┘  │   │    Cached in news_items table        │
│  ┌────────────────────┐  │   │                                      │
│  │ExecutionAgent      │  │   │  backtester.py                       │
│  │ Alpaca API calls   │  │   │    BacktestRunner: replays bars      │
│  │ retry + recovery   │  │   │    through BaseStrategy.on_bar()     │
│  └────────────────────┘  │   │    Same risk checks as live          │
│  ┌────────────────────┐  │   └─────────────────────────────────────┘
│  │HeartbeatTask       │  │
│  │ writes keepalive   │  │   ┌─────────────────────────────────────┐
│  │ to Redis every 10s │  │   │  EXTERNAL SERVICES                   │
│  └────────────────────┘  │   │  Alpaca API    broker + US data      │
└──────────────────────────┘   │  yfinance      Indian + global EOD   │
                               │  Zerodha Kite  Indian intraday*      │
┌──────────────────────────┐   │  NewsAPI       company news          │
│  CELERY BEAT (scheduler) │   │  Alpha Vantage news + financials     │
│                          │   │  Anthropic API Claude Sonnet/Haiku   │
│  Every 5 min:            │   │  * requires user's broker creds      │
│    portfolio_snapshot    │   └─────────────────────────────────────┘
│  Every 1 hour:           │
│    refresh stale news    │   ┌─────────────────────────────────────┐
│    regen stale forecasts │   │  DATABASE LAYER                      │
│  Market open:            │   │  PostgreSQL 16  (primary store)      │
│    subscribe Alpaca WS   │   │  Redis 7        (broker + pub/sub)   │
│  Market close:           │   └─────────────────────────────────────┘
│    reconcile positions   │
└──────────────────────────┘
```

---

## 6. Database Schema (complete — all tables)

See `schema.sql` for the full file. Summary of all tables:

| Table | Purpose |
|---|---|
| `tenants` | Multi-tenant root. One row per organization/user account. |
| `users` | Users within a tenant. role: owner/member. |
| `broker_connections` | Alpaca/Zerodha API keys, encrypted at rest. Per tenant. |
| `refresh_tokens` | JWT refresh token store (rotated on use). |
| `strategies` | Strategy definitions. Has `current_version_id` FK. |
| `strategy_versions` | Immutable version history. Running bots always reference a specific version. |
| `strategy_runs` | Each deploy of a strategy. Links to version, not strategy directly. |
| `positions` | Current open positions per strategy. Updated on every fill. |
| `orders` | Every order attempt (approved or rejected). Never deleted. |
| `portfolio_snapshots` | Time-series of total equity. Written by Celery Beat. Powers equity curve. |
| `backtest_results` | Stored backtest output per strategy per date range. |
| `market_data_cache` | OHLCV bar cache. Primary key: (symbol, exchange, timeframe, bar_time). |
| `news_items` | Cached company news with sentiment. |
| `forecasts` | Cached Prophet+ARIMA forecast output. |
| `notifications` | In-app notifications per user. |
| `audit_events` | Immutable audit trail. Every state change logged. |

---

## 7. API Contract

Full OpenAPI spec is regenerated via `python -m app.scripts.generate_openapi` after any route change.

```
# Auth
POST /v1/auth/register          Create tenant + owner user
POST /v1/auth/login             → {access_token, refresh_token}
POST /v1/auth/refresh           Rotate refresh token → new access_token
POST /v1/auth/logout            Invalidate refresh token

# Strategies
POST   /v1/strategies                    Create strategy (NL or code path)
GET    /v1/strategies                    List for tenant
GET    /v1/strategies/{id}               Get detail
PATCH  /v1/strategies/{id}               Edit (creates new version, does not mutate running)
DELETE /v1/strategies/{id}               Archive
POST   /v1/strategies/{id}/runs          Deploy (paper or live)
POST   /v1/strategies/{id}/backtest      Run backtest → stores result
GET    /v1/strategies/{id}/backtests     List backtest results
GET    /v1/strategies/{id}/performance   Computed metrics from live runs
GET    /v1/strategies/{id}/positions     Current open positions

# Market Data
GET  /v1/market/bars/{symbol}
     ?timeframe=1d  (1m|5m|15m|1h|4h|1d|1w)
     &limit=500
     &exchange=NASDAQ  (NASDAQ|NYSE|NSE|BSE|CRYPTO)
     &start=2024-01-01  (optional)
     &end=2024-06-01    (optional)

GET  /v1/market/indicators/{symbol}
     ?timeframe=1d
     &exchange=NASDAQ
     # indicators param uses function notation:
     &indicators=rsi(14),macd(12,26,9),bb(20,2),ema(20),ema(50),ema(200),vwap

GET  /v1/market/forecast/{symbol}
     ?horizon=5
     &exchange=NASDAQ

GET  /v1/market/news/{symbol}
     ?limit=20
     &days=7

GET  /v1/market/search?q=RELIANCE&limit=10   # Ticker autocomplete

# Portfolio
GET  /v1/portfolio/equity-curve?days=30     # Time-series from portfolio_snapshots
GET  /v1/portfolio/positions                 # All open positions across all strategies
GET  /v1/portfolio/performance               # Portfolio-level metrics

# Notifications
GET   /v1/notifications?unread_only=true
PATCH /v1/notifications/{id}/read
PATCH /v1/notifications/read-all

# Settings
GET   /v1/settings/broker
POST  /v1/settings/broker    # Save encrypted API keys
DELETE /v1/settings/broker/{broker}

# Real-time WebSocket (see Section 11 for full spec)
WS  /v1/ws/bars/{symbol}?timeframe=1m
WS  /v1/ws/portfolio
WS  /v1/ws/run/{run_id}
```

---

## 8. AutoGen Agent Specifications

### StrategyBuilderAgent
- **Purpose**: Convert NL description into a validated, deployable `BaseStrategy` Python class
- **Model**: `claude-sonnet-4-6`
- **Conversation pattern**: Multi-turn. First turn generates code. Second turn validates + self-critiques. Third turn fixes issues.
- **Input**: user NL description, available indicators list, exchange, timeframe, risk config
- **Output**: `{code: str, summary: str, edge_cases: list[str], estimated_trade_frequency: str}`
- **Tools available to agent**: `validate_python_syntax(code)`, `check_indicator_names(names)`, `sandbox_dry_run(code, sample_bars)`
- **Failure contract**: Returns `{error: str, suggestion: str}` — NEVER silently emits broken code

### RiskAgent
- **NOT LLM-based** — pure deterministic function, <1ms latency
- Location: `app/domain/risk.py`
- Contract: `verify_order_intent(order: OrderIntent, config: RiskConfig, market_state: MarketState) → RiskResult`
- `MarketState` includes: is_market_open, today_executed_notional, current_open_positions
- Returns: `{approved: bool, reason: str}`

### StrategyRunAgent (AutoGen, lives in Celery worker)
- **Purpose**: Orchestrate a live strategy run. Fetches bars → calls `on_bar()` → submits to RiskAgent → if approved, calls ExecutionAgent
- **Pattern**: AutoGen `AssistantAgent` + `UserProxyAgent` for tool use
- **Loop**: Runs on every new bar arrival via Celery periodic task or WebSocket tick

### ExecutionAgent
- **NOT LLM-based** — AutoGen `UserProxyAgent` orchestrating Alpaca API tools
- **Tools**: `place_market_order`, `place_limit_order`, `cancel_order`, `get_position`, `get_account`
- **Retry logic**: 3 retries with exponential backoff on transient Alpaca errors
- **On failure**: Logs to `audit_events`, triggers ERROR notification, does NOT retry indefinitely

### AnalysisAgent (on-demand)
- **Model**: `claude-haiku-4-5-20251001` (fast + cheap)
- **Input**: symbol, current RSI + MACD + BB + EMA values, recent 3 news headlines
- **Output**: 2–3 sentence readable market commentary
- **Rate**: Maximum 1 call per symbol per 5 minutes per user (enforced server-side)

---

## 9. BaseStrategy Interface

All strategies — AI-generated or developer-written — must subclass this. This is the contract.

```python
# app/domain/base_strategy.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

@dataclass
class StrategyContext:
    symbol: str
    exchange: str               # NASDAQ | NYSE | NSE | BSE | CRYPTO
    timeframe: str              # 1m | 5m | 15m | 1h | 4h | 1d
    bars: pd.DataFrame          # Columns: timestamp, open, high, low, close, volume (canonical)
    indicators: dict            # {"rsi_14": 42.3, "macd_12_26_9": 0.12, "bb_upper_20_2": 185.4, ...}
    position: Optional[float]   # Current held quantity. None = flat. Positive = long. Negative = short.
    avg_cost: Optional[float]   # Average cost basis of current position
    risk: "StrategyRiskConfig"
    # Multi-symbol context (populated only for multi-symbol strategies)
    peers: dict[str, "StrategyContext"] = field(default_factory=dict)

class BaseStrategy(ABC):
    def __init__(self, context: StrategyContext):
        self.ctx = context

    @abstractmethod
    def on_bar(self) -> Optional["OrderIntent"]:
        """
        Called once per bar close. Implement your trading logic here.
        Return an OrderIntent to place an order. Return None to hold.

        Available:
          self.bars           pd.DataFrame with OHLCV history
          self.indicators     dict of computed TA values for current bar
          self.position       current position size (None = flat)
          self.avg_cost       average entry price
          self.ctx.peers      other symbols' contexts if multi-symbol strategy
        """
        ...

    @property
    def bars(self) -> pd.DataFrame:
        return self.ctx.bars

    @property
    def indicators(self) -> dict:
        return self.ctx.indicators

    @property
    def position(self) -> Optional[float]:
        return self.ctx.position

    @property
    def avg_cost(self) -> Optional[float]:
        return self.ctx.avg_cost
```

---

## 10. WebSocket Architecture (full specification)

### Infrastructure
- FastAPI native WebSockets + Redis Pub/Sub as the message bus
- Alpaca WebSocket stream → FastAPI background task → publishes to Redis → WebSocket manager pushes to browser clients

### Channel Naming Convention
```
bars:{symbol}:{exchange}:{timeframe}    e.g. bars:AAPL:NASDAQ:1m
portfolio:{tenant_id}                   live P&L + notification push
run:{run_id}                            live status for a specific strategy run
```

### Message Formats (JSON)
```json
// bars channel
{
  "type": "bar",
  "symbol": "AAPL",
  "t": "2024-06-03T14:30:00Z",
  "o": 182.40, "h": 183.10, "l": 182.20, "c": 182.90, "v": 145200
}

// portfolio channel — P&L update
{
  "type": "pnl_update",
  "total_equity": 24831.50,
  "today_pnl": 312.44,
  "today_pnl_pct": 1.27,
  "positions": [{"symbol": "AAPL", "strategy_id": "...", "pnl": 48.20}]
}

// portfolio channel — notification
{
  "type": "notification",
  "id": "uuid",
  "title": "AAPL order filled",
  "body": "Bought 10 shares at $182.40",
  "category": "trade_executed"
}

// run channel — status
{
  "type": "run_status",
  "run_id": "uuid",
  "status": "running",  // queued | running | completed | failed | rejected
  "last_bar": "2024-06-03T14:30:00Z",
  "last_action": "HOLD"
}
```

### Connection Lifecycle
1. Frontend authenticates WebSocket with JWT: `wss://api/v1/ws/bars/AAPL?token=<jwt>`
2. FastAPI validates JWT on connect. Reject if invalid.
3. Server subscribes to the relevant Redis channel
4. On Redis message: push to all connected clients for that channel
5. Client sends heartbeat ping every 30s. Server closes connection after 90s of silence.

---

## 11. Market Hours & Timezone Handling

Critical: bots must not attempt orders outside market hours.

```python
# app/domain/market_hours.py

EXCHANGE_SCHEDULES = {
    "NASDAQ": {"tz": "America/New_York", "open": "09:30", "close": "16:00", "days": [0,1,2,3,4]},
    "NYSE":   {"tz": "America/New_York", "open": "09:30", "close": "16:00", "days": [0,1,2,3,4]},
    "NSE":    {"tz": "Asia/Kolkata",     "open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
    "BSE":    {"tz": "Asia/Kolkata",     "open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
    "CRYPTO": {"tz": "UTC",             "open": "00:00", "close": "23:59", "days": [0,1,2,3,4,5,6]},
}

def is_market_open(exchange: str) -> bool: ...
def get_session_status(exchange: str) -> Literal["pre_market","open","after_hours","closed"]: ...
def next_open(exchange: str) -> datetime: ...
```

The Risk Agent calls `is_market_open(exchange)` as check #1. Any order outside market hours → rejected with reason `"Market closed"`.

---

## 12. Security Architecture

### JWT Auth
- Access token: 15-minute expiry. Signed with RS256.
- Refresh token: 30-day expiry. Stored hashed in `refresh_tokens` table. Rotated on every use.
- All API endpoints require `Authorization: Bearer <token>` except `/v1/auth/*`.
- WebSocket auth: token passed as query param `?token=<jwt>` (validated on handshake, not per-message).

### Multi-Tenancy Enforcement
- Every DB query includes `WHERE tenant_id = :tenant_id` derived from the JWT payload.
- This is enforced at the repository layer, not the route layer. No route can accidentally leak cross-tenant data.
- Tenant ID is NEVER trusted from request body or headers — only from the verified JWT.

### Broker Key Encryption
- Alpaca/Zerodha API keys stored encrypted using Fernet (AES-128-CBC) in `broker_connections`.
- Encryption key stored in `BROKER_KEY_ENCRYPTION_SECRET` env var (never in DB).
- Keys are decrypted in memory only when a worker needs them. Never logged. Never returned via API.

### Developer Code Sandbox
- User-submitted Python is executed via RestrictedPython.
- Restricted environment: no `import os`, no `import subprocess`, no `import socket`, no file I/O.
- Allowed imports: `pandas`, `numpy`, `app.domain.base_strategy`, `app.domain.models`.
- Timeout: 30 seconds max execution for backtests. Celery task timeout kills anything longer.
- Memory limit: enforced via Celery worker `--max-memory-per-child`.

### Rate Limiting
- slowapi applied per-endpoint. Key: user JWT sub.
- Market data endpoints: 60 req/min per user.
- Strategy create/deploy: 10 req/min per user.
- AnalysisAgent: 12 req/hour per user (external AI cost control).

---

## 13. Backtesting Engine

```
BacktestRunner.run(
    strategy_class: Type[BaseStrategy],
    symbol: str,
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    initial_capital: float = 10000.0,
    indicator_params: dict = DEFAULT_INDICATORS,
) → BacktestResult
```

**Algorithm:**
1. Fetch full OHLCV history for date range (from cache or external)
2. Compute all indicators for each bar using pandas-ta (vectorized, not per-bar)
3. Walk forward bar by bar: build `StrategyContext` with bars up to current, call `on_bar()`
4. If `OrderIntent` returned: call `verify_order_intent()` with simulated risk state
5. If approved: simulate fill at next bar's open price (conservative assumption)
6. Track: position, avg cost, realized P&L, equity curve
7. At end: compute metrics

**Performance Metrics computed:**
- Total return %
- Annualized return %
- Sharpe ratio (risk-free rate: 5% annualized)
- Sortino ratio
- Maximum drawdown % + date range
- Win rate %
- Profit factor (gross profit / gross loss)
- Total trades, avg trade duration, avg win, avg loss

---

## 14. Data Normalization Contract

All market data, regardless of source, must be normalized to this canonical model before use:

```python
# app/domain/market_data.py
@dataclass
class Bar:
    symbol: str
    exchange: str
    timeframe: str
    timestamp: datetime     # UTC always
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
```

The `market_data.py` service is the ONLY place that calls yfinance/Alpaca. Everything else consumes `Bar` objects. No raw yfinance DataFrames or Alpaca Bar objects leak beyond that service boundary.

---

## 15. Ticker Search / Symbol Resolver

```
GET /v1/market/search?q=RELIANCE&limit=10
```

Returns matches across NSE, BSE, NASDAQ, NYSE from a static symbol list bundled with the app (updated monthly). Format:
```json
[
  {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE"},
  {"symbol": "RELIANCE.BO", "name": "Reliance Industries", "exchange": "BSE"}
]
```

User-facing display: always show `{name} ({exchange})`. Internal format: always `RELIANCE.NS`. The resolver handles the conversion transparently.

---

## 16. Celery Beat Schedule

```python
# app/core/celery_app.py — beat_schedule

beat_schedule = {
    # Portfolio snapshot every 5 minutes during market hours
    "portfolio-snapshot": {
        "task": "app.worker.beat_tasks.snapshot_portfolio",
        "schedule": crontab(minute="*/5"),
    },
    # Refresh news for all symbols with active strategies (every hour)
    "refresh-news": {
        "task": "app.worker.beat_tasks.refresh_active_symbols_news",
        "schedule": crontab(minute=0),
    },
    # Regenerate stale forecasts (older than 1 hour) every hour
    "refresh-forecasts": {
        "task": "app.worker.beat_tasks.refresh_stale_forecasts",
        "schedule": crontab(minute=30),
    },
    # Worker heartbeat check — mark workers as dead if no keepalive in 30s
    "worker-heartbeat-check": {
        "task": "app.worker.beat_tasks.check_worker_heartbeats",
        "schedule": 30.0,  # seconds
    },
    # Position reconciliation at market close (5:00 PM NY time)
    "reconcile-positions": {
        "task": "app.worker.beat_tasks.reconcile_positions",
        "schedule": crontab(hour=17, minute=0),
    },
}
```

---

## 17. Worker Crash Recovery

**Problem**: A Celery worker crashes mid-trade → position open, no bot managing it → unbounded loss.

**Solution (three-layer):**

1. **Heartbeat**: Every strategy worker writes `{run_id}: {timestamp}` to a Redis key every 10 seconds. Celery Beat's `check_worker_heartbeats` task reads all active run keys. If any is stale (>30s), it marks the run as `ERROR`, triggers an ERROR notification, and optionally executes an emergency flatten.

2. **Position Reconciliation**: At market close, `reconcile_positions` task compares `positions` table against Alpaca account positions. Any discrepancy is flagged in `audit_events` and alerted via notification.

3. **Celery Task Config**: All strategy tasks use `acks_late=True` + `reject_on_worker_lost=True`. This ensures if a worker process dies, the task is re-queued rather than silently lost.

---

## 18. Strategy Versioning

```
strategies table  ←  current_version_id (FK)
      ↑
strategy_versions table  (immutable rows)
      ↑
strategy_runs table  ←  version_id (FK, not strategy_id)
```

**Rules:**
- Creating a strategy creates `strategy_versions` row with `version_number=1`
- Editing a running strategy creates a NEW `strategy_versions` row (`version_number=2`)
- The RUNNING worker is NOT affected — it reads the version it was launched with
- Deploying after an edit deploys the latest version
- You can view any historical version's code via `GET /v1/strategies/{id}/versions/{n}`

---

## 19. Performance Metrics Service

```python
# app/services/performance.py

def compute_strategy_metrics(strategy_id: str, tenant_id: str) -> PerformanceMetrics:
    """
    Reads from orders + positions tables.
    Returns:
      - sharpe_ratio, sortino_ratio
      - max_drawdown_pct (and the date range it occurred)
      - win_rate_pct
      - profit_factor (gross_profit / abs(gross_loss))
      - total_trades, winning_trades, losing_trades
      - avg_win, avg_loss, avg_trade_duration
      - total_realized_pnl, total_unrealized_pnl
    """
```

Called by:
- `GET /v1/strategies/{id}/performance` (REST)
- Terminal → Performance tab
- Dashboard → Win Rate stat card

---

## 20. Environment Variables (see `.env.example`)

All config is managed via pydantic-settings reading from `.env`. NEVER hardcode keys.

Required variables (full list in `.env.example`):
```
DATABASE_URL          asyncpg connection string
REDIS_URL             Redis connection string
ANTHROPIC_API_KEY     Claude API key (StrategyBuilder + Analysis)
ALPACA_API_KEY        Alpaca paper trading key
ALPACA_SECRET_KEY     Alpaca paper trading secret
ALPACA_BASE_URL       https://paper-api.alpaca.markets
NEWS_API_KEY          NewsAPI.org key
ALPHA_VANTAGE_KEY     Alpha Vantage API key (news + financials)
JWT_PRIVATE_KEY       RS256 private key (PEM)
JWT_PUBLIC_KEY        RS256 public key (PEM)
BROKER_KEY_ENCRYPTION_SECRET  Fernet key for encrypting broker credentials
SENTRY_DSN            Sentry project DSN (optional in dev)
```

---

## 21. Deployment Architecture

### Target Infrastructure: Hetzner Cloud + Cloudflare + Vercel

| Service | Provider | Cost | Why |
|---|---|---|---|
| API + Workers + DB + Redis | Hetzner CX32 (4 vCPU, 8GB RAM) | ~EUR 15/month | Best price/performance. Full control. Low latency. |
| DDoS protection + SSL + CDN | Cloudflare (free tier) | Free | Terminates SSL before it hits the server. Hides origin IP. |
| Frontend | Vercel | Free | Native Next.js deployment. Zero config. |
| Managed DB (when needed) | Supabase or Hetzner Managed PG | $25+/month | Migrate to managed DB after 100+ active users. |

### Network Topology

```
Browser
  |
  | HTTPS
  v
Cloudflare (SSL termination, DDoS, CDN)
  |
  | HTTP (internal, Cloudflare handles TLS)
  v
Hetzner Server: 80/443
  |
  v
Nginx (load balancer + reverse proxy)
  |-- /v1/ws/*  ──► WebSocket upgrade ──► API containers
  |-- /v1/auth/ ──► rate: 10/min ─────► API containers
  |-- /v1/market/ ► rate: 60/min ─────► API containers
  |-- /*         ──► rate: 300/min ────► API containers
  |
  [API container 1] [API container 2] [API container 3]
  (each: uvicorn, 1 worker, 1 process)
         |
  [Celery workers: --scale worker=2, --concurrency=4]
  [Celery Beat: exactly 1 instance]
         |
  [PostgreSQL :5432 (localhost only)]
  [Redis :6379 (localhost only)]
```

### Local Development
```powershell
docker compose up -d                                         # postgres + redis + adminer
uvicorn app.main:app --reload                                # API on :8000
celery -A app.core.celery_app.celery_app worker -Q trading_tasks -c 2 --loglevel=info
celery -A app.core.celery_app.celery_app beat --loglevel=info
```

### Production Deployment
```bash
# On Hetzner server:
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --scale api=3 --scale worker=2
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### Scaling Path
- **0-100 users**: Single Hetzner CX32, 2-3 API containers, 1 worker container
- **100-1000 users**: Add second Hetzner box for Celery workers only
- **1000+ users**: Migrate to Docker Swarm or managed Kubernetes (Hetzner k8s)

---

## 22. Monetization & Broker Connection Model

### BYOB (Bring Your Own Broker) — the money model
AlphaSwarm never touches trader funds. All money lives in the trader's own regulated
broker account. AlphaSwarm sends orders via the broker's API using keys the trader provides.
This means: no money transmission license, no custody liability, no banking infrastructure.

### Money flows
```
Trading funds:
  Trader deposits money into their OWN Zerodha/Alpaca account (via broker's own app)
  Trader connects broker to AlphaSwarm via API keys (stored encrypted in broker_connections)
  AlphaSwarm sends orders → Broker executes → Money stays in trader's broker account

AlphaSwarm subscription:
  Trader pays AlphaSwarm via Stripe (international) or Razorpay (India)
  This is payment for SOFTWARE — completely separate from trading funds
```

### Broker connection UX
No manual API key pasting for brokers that support OAuth. The experience is:
  - India: "Connect Upstox" button → OAuth flow → one click, done
  - US: "Connect Alpaca" → 3-step guided wizard with screenshots (Alpaca has no OAuth)
  - India (future): Zerodha OAuth (requires paid developer account — add post-PMF)
  - NOT supported at launch: Angel One (no OAuth, poor API UX)

### Broker roadmap
| Broker | Status | Connection |
|---|---|---|
| Alpaca | Launch | Guided wizard (3 steps) |
| Upstox | Launch | OAuth button |
| Zerodha | Post-launch | OAuth (after dev fee ROI) |
| Fyers | Post-launch | OAuth |
| Others | TBD | Evaluate per user request |

### Pricing model — Founding Member launch
All features free for the first 500 users (Founding Members).
Visible counter on the landing page creates urgency without fake deadlines.
When paid tiers launch, founding members get 3 months free on the Trader plan.

| Tier | Bots | Markets | Features | Price |
|---|---|---|---|---|
| Founding Member | 5 | Paper + Live | Full | Free (500 spots) |
| Trader (coming soon) | 5 | Paper + Live | Full AI builder | INR 999/mo or $15/mo |
| Pro (coming soon) | 20 | All global | Full + code editor | INR 2999/mo or $49/mo |
| Quant (coming soon) | Unlimited | All | Everything + API | INR 7999/mo or $99/mo |

`tenants.plan` valid values: `founding_member` | `trader` | `pro` | `quant`

### Subscription billing (Phase 7)
- International: Stripe (credit card, PayPal)
- India: Razorpay (UPI, NetBanking, cards)
- These are SaaS subscription payments ONLY — zero connection to trading funds

---

## 22. Frontend Page Map (complete)

```
/                         → Redirect to /dashboard (if logged in) or /auth/login
/auth/login               → Email + password login
/auth/register            → Create account (creates tenant)
/dashboard                → Portfolio overview (equity curve, stats, bots grid, trades feed)
/terminal/[symbol]        → Market terminal for any global ticker (no strategy context)
/strategies               → List all strategies with status + quick P&L
/strategies/new           → Dual-pathway builder (NL or code)
/strategies/new?mode=code → Developer code editor path directly
/strategies/[id]          → Strategy detail with embedded terminal + performance + runs
/strategies/[id]/backtest → Backtest configuration + results view
/market/[symbol]          → Standalone market intelligence (search, chart, news, forecast)
/settings                 → Broker API keys, notification prefs, plan, profile
/settings/broker          → Connect/disconnect Alpaca, Zerodha, Angel One
```

---

## 23. Key Engineering Rules (non-negotiable)

1. **Auth is mandatory.** Every API endpoint except `/v1/auth/*` and `/health` requires a valid JWT. No exceptions for "dev mode."
2. **No LangChain.** AutoGen exclusively. If you find a LangChain import, replace it.
3. **Risk function is sacred.** `verify_order_intent()` is called before every broker API call. No bypass, no shortcut, no "it's just paper trading."
4. **Every chart is functional.** If a chart is on screen, it must answer a specific question. If you cannot state what question it answers, do not add it.
5. **No spaghetti code.** Routes contain no business logic. Services contain no SQL. DB queries in repositories only.
6. **Async throughout backend.** All DB calls via asyncpg. No synchronous I/O in the FastAPI event loop.
7. **Canonical Bar model.** Raw yfinance/Alpaca data never crosses the service boundary. Always normalized.
8. **Market hours enforced.** No orders outside trading hours. Market session status displayed in UI.
9. **Paper by default.** `paper_trading_only: true` is the default. Live trading requires explicit key configuration + opt-in.
10. **Honest forecasting.** Always labeled "Statistical projection — not financial advice." Always show confidence intervals and model error metrics.
11. **Crash recovery.** Worker heartbeats are mandatory for any long-running strategy task.
12. **NSEpy is banned.** Do not import or use NSEpy. Use yfinance for Indian EOD data.
13. **Versions are immutable.** Never mutate a `strategy_versions` row. Edit = new row.
14. **Tenant isolation.** Every SQL query includes tenant_id filter. Enforced in repository layer.

---

## CURRENT STATE & ROADMAP

- [x] Phase 0: System design v2.0 — this document. All gaps resolved.
- [x] Phase 1a: FastAPI skeleton, Pydantic models, Celery structure skeleton
- [x] Phase 1b: In-memory strategy store, basic risk function stub, schema.sql (partial)
- [x] **Phase 1c — Deployment infrastructure + backend optimization**
  - [x] `Dockerfile` — multi-stage build, non-root user, uvloop
  - [x] `docker-compose.prod.yml` — nginx LB + API scale + worker + beat + postgres + redis
  - [x] `nginx/nginx.conf` — least_conn LB, rate limiting, WebSocket upgrade, gzip
  - [x] `app/main.py` — lifespan events, ORJSONResponse, GZip middleware, split health checks
  - [x] `app/core/celery_app.py` — acks_late, prefetch=1, max-tasks-per-child, beat_schedule
  - [x] `app/worker/beat_tasks.py` — stub tasks (implemented in Phase 3/4)
  - [x] Deployment architecture documented (Hetzner + Cloudflare + Vercel)
  - [x] Monetization model documented (BYOB + Founding Member pricing)
- [x] **Phase 2 — DB Layer + Auth**
  - [x] `alembic/` — migration setup + initial migration from schema.sql
  - [x] `app/db/connection.py` — asyncpg pool wired into lifespan
  - [x] `app/db/base_repo.py` — base repository with tenant_id filter enforcement
  - [x] `app/db/repositories/` — users, strategies, runs
  - [x] `app/api/routes.py` — strategy routes migrated from in-memory to DB repos
  - [x] `app/api/auth.py` — register, login, refresh, logout endpoints (RS256/HS256)
  - [x] `app/api/deps.py` — JWT dependency injection (CurrentUser)
  - [x] `app/services/auth.py` — JWT sign/verify + bcrypt + refresh token service
  - [x] `tenants.plan` supports: founding_member | trader | pro | quant
- [x] Phase 3 — Market Data & Intelligence (3A + 3B QA complete, 3C pending)
  - [x] **Phase 3A — Broker Integration (BYOB)** ✓ QA verified 2026-06-03
    - [x] `app/services/broker_crypto.py` — Fernet AES-256 + PBKDF2HMAC key derivation (390k iterations); no hardcoded fallback; lru_cache
    - [x] `app/db/repositories/brokers.py` — BrokerRepo (tenant-scoped upsert/list/delete)
    - [x] `app/api/brokers.py` — POST /v1/brokers, GET /v1/brokers, DELETE /v1/brokers/{id}, PATCH /v1/brokers/{id}/test; URL validation; Alpaca account status check
    - [x] Alpaca connection validated via live API ping before storing credentials
    - [x] `frontend/src/app/settings/brokers/page.tsx` — broker management UI (connect, list, test, remove); delete error banner; live-trading confirmation
    - [x] Sidebar Settings link active → /settings/brokers
  - [x] `app/domain/market_data.py` — canonical Bar model + Exchange/Timeframe enums
  - [x] `app/domain/market_hours.py` — exchange schedules, is_market_open, get_session_status
  - [x] **Phase 3B — Market Data Service** ✓ QA verified 2026-06-03
    - [x] `app/db/repositories/market_data.py` — MarketDataRepo (bulk upsert, get_bars, latest_bar_time); Decimal precision; UTC-aware timestamps
    - [x] `app/services/market_data.py` — Alpaca (primary) + yfinance fallback; 4h aggregation from 1h; stale cache fallback; full-history upsert (limit applied after cache write, not before)
    - [x] `app/services/indicators.py` — pandas-ta: rsi, macd, bb, ema, sma, vwap, atr, stoch, roc; regex-based spec parser (multi-arg indicators correct)
    - [x] `app/services/symbol_search.py` — static symbol DB (NASDAQ/NYSE/NSE/BSE/Crypto), prefix+name search; 15 BSE + 20 NSE symbols
    - [x] `app/api/market.py` — GET /v1/market/bars/{symbol}, /v1/market/indicators/{symbol}, /v1/market/search; 60/min rate limiting per JWT user
    - [x] `app/core/rate_limit.py` — JWT-aware slowapi key function; wired into main.py
    - [x] `app/ws/manager.py` — WebSocketManager + Redis pub/sub bridge (bars/portfolio/run channels)
    - [x] `app/api/ws.py` — /v1/ws/bars/{symbol}, /v1/ws/portfolio, /v1/ws/run/{run_id} with JWT auth + tenant ownership check + zombie connection cleanup
  - [x] **Phase 3C — Intelligence Layer** ✓ 2026-06-04
    - [x] `app/db/repositories/intelligence.py` — ForecastRepo + NewsRepo (not tenant-scoped)
    - [x] `app/services/forecaster.py` — Prophet + ARIMA ensemble; asyncio.to_thread for CPU work; 1hr cache
    - [x] `app/services/news_intel.py` — NewsAPI (primary) + Alpha Vantage (secondary) + Claude Haiku batch sentiment
    - [x] `GET /v1/market/forecast/{symbol}` — ?horizon=5&exchange=NASDAQ; 60/min rate limited
    - [x] `GET /v1/market/news/{symbol}` — ?days=7&limit=20; 60/min rate limited
    - [x] Beat tasks implemented: `refresh_active_symbols_news` (hourly :00), `refresh_stale_forecasts` (hourly :30)
- [ ] Phase 4 — Execution Engine
  - [ ] `app/domain/base_strategy.py` — BaseStrategy + StrategyContext (multi-symbol support)
  - [ ] `app/domain/risk.py` — expand with market hours check + position limits
  - [ ] `app/services/execution.py` — Alpaca order placement, position tracking
  - [ ] `app/worker/tasks.py` — real StrategyRunAgent using AutoGen + BaseStrategy
  - [ ] Worker heartbeat + crash recovery
  - [ ] Position reconciliation beat task
- [ ] Phase 5 — Strategy Builder & Backtesting
  - [ ] `app/services/strategy_builder_agent.py` — AutoGen StrategyBuilderAgent (real NL→code)
  - [ ] `app/services/backtester.py` — BacktestRunner + PerformanceMetrics
  - [ ] `app/domain/sandbox.py` — RestrictedPython sandbox for user code
  - [ ] Strategy versioning (new version on edit, run links to version)
  - [ ] `app/services/performance.py` — live performance metrics from orders/positions
- [ ] Phase 6 — Frontend
  - [ ] Auth pages (login, register) + JWT token management
  - [ ] Dashboard with real WebSocket equity curve + live P&L
  - [ ] Trading terminal with TradingView candlestick + TA sub-charts
  - [ ] Forecast tab + News tab + Performance tab + AI Analysis tab
  - [ ] Dual-pathway strategy builder (NL form + Monaco code editor)
  - [ ] Backtest results view (equity curve overlay + metrics card)
  - [ ] Market intelligence page with ticker search
  - [ ] Settings page (broker key management)
  - [ ] Notification panel (real-time + history)
  - [ ] Market hours status badge throughout
- [ ] Phase 7 — Production Hardening
  - [x] slowapi rate limiting on all market endpoints (60/min per JWT user) — done in Phase 3B
  - [ ] Sentry error + performance monitoring
  - [ ] Live trading gate (Alpaca live key validation before enabling)
  - [ ] Email notification delivery (SendGrid)
  - [ ] Subscription/billing hooks (Stripe)
  - [ ] Indian intraday data via Zerodha Kite Connect (user provides credentials)
  - [ ] Load testing + connection pool tuning
  - [ ] CI/CD pipeline (GitHub Actions → Docker build → deploy)

---

## Agent Execution Notes

**Starting Phase 2?**
- Begin with `docker-compose.yml` + `schema.sql` update + alembic init. Nothing else works without the DB.
- `app/core/config.py` must be done before any service since everything reads env vars from it.
- Auth (JWT) must be done in Phase 2, not deferred. Multi-tenancy is impossible without it.
- The `app/db/` directory needs: `connection.py` (asyncpg pool), `base_repo.py` (base class with tenant_id filter enforcement).

**Starting Phase 3?**
- Phase 2 DB must be complete first. Market data cache requires the DB.
- Always use `Bar` canonical model. Never return raw yfinance or Alpaca objects from `market_data.py`.
- Use `yfinance` for Indian data. `SYMBOL.NS` = NSE, `SYMBOL.BO` = BSE. Do NOT use NSEpy.
- Celery Beat config goes in `app/core/celery_app.py`.

**Starting Phase 5?**
- Test `StrategyBuilderAgent` output against real execution. The agent must generate code that `BacktestRunner` can actually run, not pseudo-code.
- RestrictedPython sandbox must be tested with malicious input before Phase 6 frontend opens the code editor to users.

**Starting Phase 6?**
- `lightweight-charts` from TradingView is the ONLY charting library. Do not substitute.
- TradingView chart goes in its own React component with `useRef` for the DOM mount.
- WebSocket connections must reconnect automatically on disconnect (exponential backoff, max 30s).
- All monetary values displayed with locale-appropriate formatting (INR for Indian symbols, USD for US).
