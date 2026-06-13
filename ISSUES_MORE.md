# AlphaSwarm Phase 5 Issues - Part 2 (Critical Risk & Core Bugs)

> **STATUS: ✅ ALL RESOLVED.** Issues 5–8 are fixed. A second wave of follow-up risk/security bugs found afterward is listed below as 9–14, also all fixed.

## 5. Short Selling Completely Bypasses Position Risk Limits
**Status:** ✅ FIXED — Checks 4a/4b now use exposure-direction logic, so shorts are capped by `max_position_notional` / `max_open_positions` too.
**Location:** `app/domain/risk.py` (Checks 4a & 4b)
**Description:** The risk engine enforces the `max_position_notional` and `max_open_positions` limits with an explicit `if order.side == OrderSide.buy:` check. As a result, an AI agent can issue unlimited `OrderSide.sell` signals to open short positions, completely bypassing the position caps and max concurrent trades limit. This is a severe violation of the "RISK IS SACRED" rule.

## 6. "Risk-Reducing" Trades Bypass Daily Turnover Limits on Directional Flips
**Status:** ✅ FIXED — only the genuinely closing quantity is exempt; the exposure-increasing remainder of an oversized flip counts toward the daily cap.
**Location:** `app/domain/risk.py` (Check 5)
**Description:** The `is_risk_reducing` logic exempts an order from the daily turnover cap if the order is opposite to the current position (e.g., selling when currently long). However, it does not check the order quantity. If an agent holds 1 share long and decides to sell 10,000 shares, the system sees it as "closing a long" and exempts the entire order, allowing a massive short position to blow past the daily notional limit.

## 7. Hardcoded "NASDAQ" Breaks Multi-Market & Crypto Trading
**Status:** ✅ FIXED — exchange is threaded through from the strategy; no hardcoded `"NASDAQ"`.
**Location:** `app/worker/tasks.py` and `app/api/routes.py`
**Description:** The execution worker and the API router hardcode `"NASDAQ"` as the exchange when fetching bars, checking session status, and creating the `StrategyContext`. This means Crypto and NSE (Indian market) strategies will incorrectly be evaluated against US trading hours, causing them to be rejected when they should be open, and vice-versa. 

## 8. Sandbox Escape / RCE Risk via Raw Pandas DataFrame
**Status:** ✅ FIXED — the `StrategyContext` now receives the `ReadOnlyDataFrame` wrapper (hardened to fully convert bars to native Python).
**Location:** `app/worker/tasks.py`
**Description:** The `StrategyContext` is instantiated with `bars=bars_df` (a raw pandas DataFrame). `app/domain/base_strategy.py` explicitly defines a `ReadOnlyDataFrame` wrapper to prevent malicious or broken AI-generated code from accessing dangerous Pandas internals inside the `RestrictedPython` sandbox. Because the raw DataFrame is passed instead of the wrapper, the sandbox isolation is effectively broken.

---

# Follow-up Wave (Risk / Security / Wiring) — ✅ ALL FIXED

## 9. Daily-Cap TOCTOU Double-Place + Released-Connection Phantom Orders
**Status:** ✅ FIXED — `pg_advisory_xact_lock` plus a single DB connection held across the whole read→check→place→persist sequence.
**Location:** `app/worker/tasks.py`
**Description:** The read→check→place→persist sequence was not atomic, so concurrent workers could both pass the daily-notional cap and double-place, and a connection released mid-flight could persist a phantom order.

## 10. FX-Blind Platform Cap (INR notional vs USD cap)
**Status:** ✅ FIXED — `broker_routing.py` is now the single FX source of truth (`PLATFORM_CAP_CURRENCY`, `_UNITS_PER_USD`, `convert_amount`); risk Check 6 converts the USD platform cap into the order's currency before comparing.
**Location:** `app/domain/risk.py` (Check 6)
**Description:** Check 6 compared an INR-denominated order notional directly against the USD `settings.default_max_order_notional` with no conversion, so the platform-level cap was effectively ~83× too loose for NSE/BSE orders. The user-facing message also mixed ₹ and $.

## 11. `reconcile_positions` Hardcoded to Alpaca
**Status:** ✅ FIXED — fetches all active `broker_connections` and routes each via `get_executor(row["broker"], …)`; logs include the broker name.
**Location:** `app/worker/beat_tasks.py`
**Description:** The end-of-day reconciliation only queried Alpaca connections and always built an `AlpacaExecutor`, so any non-Alpaca broker (e.g. Upstox/NSE) was silently never reconciled.

## 12. Hardcoded `$` in Risk-Pass Log
**Status:** ✅ FIXED — uses `currency_symbol()` (`_cur`) like the rest of the worker.
**Location:** `app/worker/tasks.py`
**Description:** The `"PASSED — notional $..."` log line hardcoded `$`, mislabeling INR (₹) order notionals.

## 13. Static PBKDF2 Salt for Broker-Key Encryption
**Status:** ✅ FIXED — per-record random 16-byte salt stored in a `v2:<b64salt>:<token>` envelope; legacy static-salt ciphertext still decrypts.
**Location:** `app/services/broker_crypto.py`
**Description:** Every encrypted broker key derived its Fernet key from one shared static salt, so identical secrets produced correlated keys and the salt provided no per-record protection.

## 14. No Guard Enforcing the "Platform Never Handles Funds" Invariant
**Status:** ✅ FIXED — `tests/test_no_fund_custody.py` fails the build if deposit/withdraw/custody/wallet/escrow/payout/etc. code appears under `app/`.
**Location:** `tests/`
**Description:** The product invariant (no custody/wallet/deposit/withdrawal logic) was only documented, not enforced, so it could silently rot.
