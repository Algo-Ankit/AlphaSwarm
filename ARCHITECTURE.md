# Agentic Trading SaaS - Master Context

**Objective:** A multi-tenant SaaS platform where non-coders use AI agents to build and deploy parallel algorithmic trading bots.

## 1. Technology Stack
- **Frontend:** Next.js (React), TailwindCSS, Lightweight Charts.
- **Backend / Control Plane:** FastAPI, PostgreSQL.
- **Execution Plane:** Celery (Background workers for parallel trading bots), Redis (Message broker).
- **Broker API:** Alpaca (Paper Trading by default).
- **AI Engine:** LLM API (Translates user natural language into Python logic).

## 2. Architecture Rules
- **Decoupled Engine:** The FastAPI server ONLY handles API requests. All trading logic runs in isolated Celery background workers.
- **Risk Management:** All execution commands must pass through a centralized risk verification function before hitting the Alpaca API.
- **Token Efficiency:** This document must remain terse. Do not copy/paste code here.

## 3. Agent Communication Protocol
When an AI agent (Claude, Codex, Antigravity) completes a task:
1. Update the `CURRENT STATE` section below.
2. Keep updates to 1-2 bullet points.
3. For API documentation, refer agents to the generated `openapi.json` rather than explaining endpoints in text.

---

## CURRENT STATE & ROADMAP
- [x] Project scope and System Design finalized.
- [x] Phase 1: Initialize FastAPI project structure and PostgreSQL database schema.
- [ ] Phase 2: Configure Celery and Redis for parallel isolated background workers.
- [ ] Phase 3: Implement Alpaca API integration within the worker logic.
- [ ] Phase 4: Initialize Next.js frontend and build the chat interface.
