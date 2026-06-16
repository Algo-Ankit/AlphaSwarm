# Persistent Brain (AlphaSwarm)

**STATE TRACKING:**
- **Phases 0-7:** COMPLETE (Backend, DB, Market Data, Execution Engine, Strategy Builder & Backtesting, Frontend, Production Hardening).
- **Current Phase:** PHASE 8 (Global Platform) — COMPLETE. Next: Sentry, Stripe, SendGrid, CI/CD (carried from Phase 7).
- When a phase is done, briefly edit the ROADMAP at the very bottom of `ARCHITECTURE.md`. Do not rewrite the whole file.

**HARD RULES (NON-NEGOTIABLE):**
1. **NO LANGCHAIN:** Use the Microsoft Agent Framework (`agent-framework-core`) exclusively. AutoGen is retired (maintenance-only since Agent Framework GA 1.0, April 2026) — do not reintroduce `autogen-*` packages.
2. **RISK IS SACRED:** `verify_order_intent()` MUST run before every broker API call. No bypasses.
3. **INDICATORS:** Use `pandas-ta` exclusively.
4. **DATA:** Use canonical `Bar` model. `NSEpy` is banned. Use `yfinance` for Indian data.
5. **DATABASE:** `asyncpg` only. No sync I/O. All queries must enforce `tenant_id`.

**CONTEXT EFFICIENCY:**
- DO NOT read `ARCHITECTURE.md`, `openapi.json`, or `schema.sql` automatically.
- Only read them if explicitly tagged or asked, and read them surgically.
- Code output must be concise. Do not explain steps in long paragraphs.
