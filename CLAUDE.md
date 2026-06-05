# Persistent Brain (AlphaSwarm)

**STATE TRACKING:**
- **Phases 0-4:** COMPLETE (Backend, DB, Market Data, Execution Engine).
- **Current Phase:** PHASE 5 (Strategy Builder & Backtesting).
- **Goal:** AutoGen `StrategyBuilderAgent`, `BacktestRunner`, `RestrictedPython` sandbox.
- When Phase 5 is done, briefly edit the ROADMAP at the very bottom of `ARCHITECTURE.md`. Do not rewrite the whole file.

**HARD RULES (NON-NEGOTIABLE):**
1. **NO LANGCHAIN:** Use Microsoft AutoGen exclusively.
2. **RISK IS SACRED:** `verify_order_intent()` MUST run before every broker API call. No bypasses.
3. **INDICATORS:** Use `pandas-ta` exclusively.
4. **DATA:** Use canonical `Bar` model. `NSEpy` is banned. Use `yfinance` for Indian data.
5. **DATABASE:** `asyncpg` only. No sync I/O. All queries must enforce `tenant_id`.

**CONTEXT EFFICIENCY:**
- DO NOT read `ARCHITECTURE.md`, `openapi.json`, or `schema.sql` automatically.
- Only read them if explicitly tagged or asked, and read them surgically.
- Code output must be concise. Do not explain steps in long paragraphs.
