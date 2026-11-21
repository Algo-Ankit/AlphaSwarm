# Persistent Brain (AlphaSwarm)

**CURRENT STATE:**
- **Phases 0–12 (MVP Core):** Built (FastAPI + `asyncpg` + Alembic `0001–0014` + Celery 5/Redis 7 + Next.js 14).
- **Active Sprint Order:**
  1. Repo Hygiene (done)
  2. **Track 1:** Critical bugfixes & production wiring (done)
  3. **AI Layer Upgrade:** Default Google Gemini models + user model picker + NVIDIA NIM + full BYOK override (done)
  4. **Track 2:** Core MVP completion: live execution UI/scheduling, `/runs` page, Zerodha & Angel One executors, copy-trading polish, real CAS/broker upload (done)
  5. **Track 3:** Post-MVP roadmap (Tax-Loss Harvesting, RBI Account Aggregator, Corporate Actions, TimescaleDB/WS feed handler, SEBI peak-margin)

**HARD RULES (NON-NEGOTIABLE):**
1. **NO LANGCHAIN / NO AUTOGEN:** Use Microsoft Agent Framework (`agent-framework-core` + `agent-framework-openai`) exclusively.
2. **RISK IS SACRED:** `verify_order_intent()` MUST run before every broker API call (live, backtest, copy-trade). No bypasses.
3. **NO FUND CUSTODY (BYOB):** Never add deposit, withdraw, wallet, escrow, or custody logic (`tests/test_no_fund_custody.py` enforces this).
4. **INDICATORS:** Use `pandas-ta` exclusively. No TA-Lib.
5. **DATA:** Canonical `Bar` model only. `NSEpy` is banned. Use Alpaca (US/crypto) and `yfinance` (Indian/global EOD) + broker APIs.
6. **DATABASE:** `asyncpg` only. No blocking sync I/O on the FastAPI event loop. All tenant-scoped queries enforce `tenant_id` via `BaseRepo`.
7. **SECRETS:** Never commit real API keys or secrets; store only in `.env` (gitignored) or encrypted at rest in DB.

**DOCS & CONTEXT EFFICIENCY:**
- Read `docs/HANDOVER.md` for current status, known bugs, and active backlog.
- Read `docs/DECISIONS.md` for architecture decision records (ADRs) and rationale.
- Do NOT read `docs/ARCHITECTURE.md`, `openapi.json`, or `schema.sql` automatically — read surgically only when needed.
- Keep code changes and explanations concise.
