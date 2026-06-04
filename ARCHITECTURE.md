# AlphaSwarm — Master System Design & Architecture (Optimized)

## 1. System Overview
AlphaSwarm is a production-grade algorithmic trading SaaS. 
- **Backend:** FastAPI + asyncpg (PostgreSQL) + Celery (Redis). 
- **AI/Agents:** Microsoft AutoGen (pyautogen) + Claude Sonnet 4.6.
- **Frontend:** Next.js 14 App Router + TradingView Lightweight Charts + Zustand + Tailwind.
- **Data:** Alpaca (US), yfinance (Global/India EOD), NewsAPI, Alpha Vantage.
- **Auth & Sec:** JWT (python-jose), bcrypt, Fernet encryption for broker keys.

## 2. API Contract (Summary)
- `POST /v1/auth/login` (JWT)
- `/v1/strategies/*` (CRUD, Deploy, Backtest)
- `/v1/market/*` (Bars, Indicators, Forecast, News, Search)
- `/v1/portfolio/*` (Equity Curve, Positions)
- `WS /v1/ws/*` (Bars, Portfolio, Run Status)

## 3. Key Engineering Rules
1. **Auth is mandatory.** Every API endpoint requires JWT.
2. **No LangChain.** AutoGen exclusively.
3. **Risk function is sacred.** `verify_order_intent()` cannot be bypassed.
4. **Tenant isolation.** Every SQL query includes tenant_id.
5. **Paper by default.** Live trading requires explicit opt-in.
6. **Flexible LLM Strategy (BYOK & Local-First).** Users can provide their own Anthropic/OpenAI keys (BYOK) OR use a local GPU model (e.g. Ollama) for 100% free operation. AutoGen and News Intel must support this dynamic fallback.
## CURRENT STATE & ROADMAP
- [x] Phase 0-2: COMPLETE (DB, Auth, Multi-tenancy, Docker, Celery setup)
- [x] Phase 3: Market Data & Intelligence COMPLETE (Broker BYOB, Market Data cache, Forecast, News, WebSockets)
- [ ] Phase 4: Execution Engine
  - [ ] `app/domain/base_strategy.py`, `app/domain/risk.py`
  - [ ] `app/services/execution.py` (Alpaca orders)
  - [ ] `app/worker/tasks.py` (Real StrategyRunAgent via AutoGen)
  - [ ] Worker heartbeat + Position reconciliation
- [ ] Phase 5: Strategy Builder & Backtesting
  - [ ] AutoGen StrategyBuilderAgent (NL to code)
  - [ ] BacktestRunner + RestrictedPython Sandbox
- [ ] Phase 6: Frontend UI
  - [ ] Dashboard + Trading terminal (TradingView charts)
  - [ ] Strategy builder UI + Backtest results
- [ ] Phase 7: Production Hardening
  - [ ] Sentry, Email, Stripe Billing, CI/CD

## Agent Execution Notes
**Starting Phase 4?**
- You must build `app/worker/tasks.py` to evaluate strategies and place trades via Alpaca. Ensure worker heartbeats are implemented.

**Starting Phase 5/6?**
- Test Sandbox with malicious input.
- Use `lightweight-charts` for frontend.
