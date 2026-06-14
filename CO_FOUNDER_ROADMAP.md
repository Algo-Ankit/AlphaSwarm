# AlphaSwarm Co-Founder Audit & SIP Master Roadmap

> **CONFIDENTIAL: INTERNAL AUDIT**
> This document contains a brutal, unvarnished architectural review of the AlphaSwarm product, identifying critical failure points in the execution engine, and the precise roadmap required to pivot towards the **Investment Advisor & SIP** model.

---

## 1. The Quant & Execution Reality Check (Critical Bugs)
Our current trading engine is an MVP. If we deployed real capital today, it would fail catastrophically under specific market conditions.

- **The Partial Fill Disaster:** The `AlpacaExecutor.place_order()` forces a `partially_filled` status into a `filled` status. If we order 10,000 shares and get 10, the database tracks it as 100% complete. This will completely break position sizing and risk management in a live environment.
- **Limit Order Slippage Bug:** The backtester models slippage blindly by adding `slippage_bps` to the open price. It applies this even to limit orders, meaning our backtests are hallucinating limit buys *above* the limit price. 
- **The Stale Price Gap:** The Daily Notional Risk Cap (`Check 5`) uses `order.estimated_price` (usually the last close). If a stock gaps wildly at the open, the risk engine will approve the trade based on yesterday's cheap price, allowing the system to blow past the user's daily loss limits.
- **Zero Bid/Ask Spread:** The backtester assumes instant liquidity at the next tick, completely ignoring the bid/ask spread. 

## 2. The Product Manager Reality Check (The SIP Pivot)
You want to build an "Investment Advisor for Stock Portfolios and SIPs." This is a billion-dollar pivot, but our BYOB (Bring Your Own Broker) flow is not built for India yet.

- **The "Daily Token" Expiration Problem:** Indian brokers (Zerodha/Upstox) forcefully expire OAuth access tokens every single day. You cannot run a background monthly SIP if the token dies daily. **Fix:** We either need a daily push notification ("Tap to authorize today's SIP execution"), or we must integrate with a gateway like Smallcase Gateway to bypass this limitation.
- **The Fractional Share Illusion:** Our database uses `NUMERIC(18,8)` for stock quantities. India does *not* allow fractional equity shares. If a user sets a ₹2,000 SIP and the stock costs ₹5,000, our engine crashes. **Fix:** We must build a strict integer-rounding allocation algorithm.
- **The Missing e-NACH Flow:** True SIPs pull money automatically. We currently expect users to manually fund their broker accounts. **Fix:** We need to integrate Razorpay/Digio to capture e-NACH or UPI AutoPay mandates to automate fund transfers before the SIP fires.
- **Database Schema Gaps:** We need entirely new tables: `user_risk_profiles` (KYC/Risk Tolerance), `model_portfolios` (Asset weights), and `sip_mandates`.

## 3. The Backend Architect Reality Check (Scaling at 10k Users)
- **Celery Crash Vulnerability:** If a Hetzner node reboots mid-trade, the Celery task is lost. We need to implement `acks_late=True` so incomplete trades are securely re-queued.
- **No Broker Retry Logic:** If the Alpaca/Upstox API returns a `502 Bad Gateway`, the worker throws a `RuntimeError` and dies. We must implement exponential backoff (e.g., using the `tenacity` library).
- **Unprotected WebSockets:** The `/v1/ws/portfolio` endpoint has zero rate-limiting. A malicious actor could open 10,000 connections and DoS our Redis Pub/Sub cluster instantly.

## 4. The UX/UI Critic Reality Check
- **Mobile Layout is Broken:** The sidebar has a hardcoded `w-[240px]` width, and the main layout assumes `ml-[240px]`. There is no hamburger menu. If a user opens this on a mobile phone to check their SIPs, half the app is literally clipped off-screen.
- **No Next.js Error Boundaries:** The `src/app/` directory lacks `error.tsx` and `global-error.tsx`. If an API call fails, the entire React tree will unmount and display Next.js's ungraceful default crash screen.
- **Flash of Unauthenticated Content:** We are missing a `middleware.ts` to protect edge routes. Authentication is done via `useEffect` client-side, causing a brief UI flash or data leak before redirecting to `/login`.
- **Zero Onboarding Flow:** Users are currently dumped into a complex terminal. We need a sleek modal sequence for: "Connect Broker -> Take Risk Assessment -> Choose SIP Portfolio."
- **Missing Loading States:** Charts and PnL pop in abruptly. We need Next.js React Suspense boundaries and skeleton loaders to make the app feel like a premium institutional product.
- **No Billing Engine:** We have no Stripe integration. To be a SaaS, we need a pricing tier UI (e.g., Free = 1 AI bot, Advisor Tier = Unlimited SIPs).
- **Missing Toast Notifications:** There is no global toast library (like `sonner`). If a socket disconnects or an API fails silently, the user has zero feedback.

## 5. Institutional-Grade Blindspots (Advanced Gaps)
If we want to manage millions of dollars (AUM) and not just run a retail hobby project, we have massive infrastructure and compliance blindspots:

- **The Corporate Action Blackhole:** There is zero logic to handle stock splits, bonuses, dividends, or mergers. If an Indian stock announces a 2:1 split, our backtester and live P&L will show a massive 50% "loss" overnight. We need a daily corporate actions ingestion pipeline to adjust historical prices and current holdings.
- **Tax-Averse Routing (FIFO/LIFO):** Indian taxation (STCG vs LTCG) is critical for a wealth advisor. Our execution engine just sells shares. It has no intelligence to perform Tax-Loss Harvesting or optimize the specific tax lots being sold.
- **SEBI Peak Margin Penalties:** Indian brokers enforce strict intraday and peak margin rules. If our algorithm miscalculates cash and places a trade that dips into uncleared margins, the user will be hit with a SEBI peak margin penalty fee, and they will blame us. The risk engine has no concept of "cleared vs uncleared" cash.
- **Market Data Bottlenecks:** Currently, strategies fetch their own data. If 10,000 users run SIPs concurrently, we will instantly hit API rate limits on our market data providers (e.g., Yahoo/Upstox). We need a centralized Feed Handler using a time-series database (like TimescaleDB) to multiplex one data stream to thousands of users.
- **Circuit Breakers & Pre-Open:** Indian markets have strict Upper/Lower circuits (5%, 10%, 20%). A market order placed on a stock hitting an upper circuit will hang and get rejected. We have no logic to detect circuit limits, nor the ability to place orders in the 9:00 AM - 9:15 AM pre-open matching session.

---

## 🚀 The Execution Plan for Opus (Next Steps)

If you have assigned Claude Opus to build the Investment Advisor & SIP feature, here is the exact order they must tackle the architecture:

1. **Phase 1: The Database Expansion:** Write the Alembic migrations for the Advisor tables (`user_risk_profiles`, `model_portfolios`, `sip_mandates`).
2. **Phase 2: The Fractional Share & Partial Fill Fix:** Refactor the math in `verify_order_intent` and `backtest.py` to strictly enforce integer shares and handle partial fills.
3. **Phase 3: The Indian OAuth Flow:** Refactor the `broker_connections` table to store `access_token`, `refresh_token`, and handle the daily OAuth redirect dance required by Indian regulators.
4. **Phase 4: The SIP Cron Engine:** Create a Celery Beat schedule (`run_sips_daily`) that wakes up, checks `sip_mandates`, calculates the integer drift, and fires off batch orders.
5. **Phase 5: Corporate Actions & Margin Safety:** Build the pipeline to ingest splits/dividends and harden the risk engine against SEBI peak margin rules.
