# AlphaSwarm Phase 5 Issues - Part 2 (Critical Risk & Core Bugs)

## 5. Short Selling Completely Bypasses Position Risk Limits
**Location:** `app/domain/risk.py` (Checks 4a & 4b)
**Description:** The risk engine enforces the `max_position_notional` and `max_open_positions` limits with an explicit `if order.side == OrderSide.buy:` check. As a result, an AI agent can issue unlimited `OrderSide.sell` signals to open short positions, completely bypassing the position caps and max concurrent trades limit. This is a severe violation of the "RISK IS SACRED" rule.

## 6. "Risk-Reducing" Trades Bypass Daily Turnover Limits on Directional Flips
**Location:** `app/domain/risk.py` (Check 5)
**Description:** The `is_risk_reducing` logic exempts an order from the daily turnover cap if the order is opposite to the current position (e.g., selling when currently long). However, it does not check the order quantity. If an agent holds 1 share long and decides to sell 10,000 shares, the system sees it as "closing a long" and exempts the entire order, allowing a massive short position to blow past the daily notional limit.

## 7. Hardcoded "NASDAQ" Breaks Multi-Market & Crypto Trading
**Location:** `app/worker/tasks.py` and `app/api/routes.py`
**Description:** The execution worker and the API router hardcode `"NASDAQ"` as the exchange when fetching bars, checking session status, and creating the `StrategyContext`. This means Crypto and NSE (Indian market) strategies will incorrectly be evaluated against US trading hours, causing them to be rejected when they should be open, and vice-versa. 

## 8. Sandbox Escape / RCE Risk via Raw Pandas DataFrame
**Location:** `app/worker/tasks.py`
**Description:** The `StrategyContext` is instantiated with `bars=bars_df` (a raw pandas DataFrame). `app/domain/base_strategy.py` explicitly defines a `ReadOnlyDataFrame` wrapper to prevent malicious or broken AI-generated code from accessing dangerous Pandas internals inside the `RestrictedPython` sandbox. Because the raw DataFrame is passed instead of the wrapper, the sandbox isolation is effectively broken.
