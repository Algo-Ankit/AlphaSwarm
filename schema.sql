-- AlphaSwarm — Complete PostgreSQL Schema
-- Run: psql -U postgres -d alphaswarm -f schema.sql
-- Migrations via Alembic after initial setup.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TENANCY & USERS
-- ============================================================

CREATE TABLE tenants (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT NOT NULL,
    plan         TEXT NOT NULL DEFAULT 'founding_member', -- founding_member | trader | pro | quant
    max_bots     INT  NOT NULL DEFAULT 5,
    -- ── Billing (Stripe) ──────────────────────────────────────────────
    -- subscription_status gates LIVE agent deployment. 'active'/'trialing'
    -- on the Quant Tier unlocks live trading; everything else is paper-only.
    stripe_customer_id              TEXT,
    stripe_subscription_id          TEXT,
    subscription_status             TEXT NOT NULL DEFAULT 'inactive', -- inactive | active | trialing | past_due | canceled
    subscription_current_period_end TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tenants_stripe_customer ON tenants(stripe_customer_id);

CREATE TABLE users (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'member', -- owner | member
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

CREATE TABLE refresh_tokens (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash         TEXT NOT NULL UNIQUE,        -- SHA-256 of the actual token
    expires_at         TIMESTAMPTZ NOT NULL,
    grace_period_until TIMESTAMPTZ,                 -- old token stays valid until this (concurrent-request race window)
    rotated_to_hash    TEXT,                        -- hash of the replacement token (for audit)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);

-- ============================================================
-- BROKER CONNECTIONS
-- ============================================================

CREATE TABLE broker_connections (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    broker           TEXT NOT NULL DEFAULT 'alpaca', -- alpaca | zerodha | angel_one
    key_encrypted    TEXT,             -- Fernet-encrypted API key (nullable for OAuth)
    secret_encrypted TEXT,             -- Fernet-encrypted API secret (nullable for OAuth)
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at TIMESTAMPTZ,
    base_url         TEXT,
    is_paper         BOOLEAN NOT NULL DEFAULT true,
    is_active        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, broker)
);

-- ============================================================
-- STRATEGIES & VERSIONING
-- ============================================================

CREATE TABLE strategies (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    description          TEXT,
    symbols              TEXT[] NOT NULL DEFAULT ARRAY['SPY'],
    exchange             TEXT NOT NULL DEFAULT 'NASDAQ',
    timeframe            TEXT NOT NULL DEFAULT '1d',
    status               TEXT NOT NULL DEFAULT 'draft', -- draft | active | paused | archived
    creation_mode        TEXT NOT NULL DEFAULT 'nl',    -- nl | code
    prompt               TEXT NOT NULL DEFAULT '',      -- original NL description (empty for code path)
    risk_config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    current_version_id   UUID,                          -- FK set after first version created
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategies_tenant_status ON strategies(tenant_id, status);
-- FK indexes: owner_user_id + current_version_id (both REFERENCES, no covering index).
CREATE INDEX idx_strategies_owner   ON strategies(owner_user_id);
CREATE INDEX idx_strategies_current_version ON strategies(current_version_id);

CREATE TABLE strategy_versions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id     UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version_number  INT  NOT NULL DEFAULT 1,
    generated_logic TEXT NOT NULL,   -- The actual Python code. IMMUTABLE after insert.
    explanation     TEXT NOT NULL DEFAULT '', -- Plain-English summary of this version (NL strategies)
    prompt_snapshot TEXT NOT NULL DEFAULT '', -- NL prompt at time of this version
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID REFERENCES users(id),
    UNIQUE (strategy_id, version_number)
);
CREATE INDEX idx_strategy_versions_strategy ON strategy_versions(strategy_id, version_number DESC);
-- FK index: created_by (REFERENCES users).
CREATE INDEX idx_strategy_versions_created_by ON strategy_versions(created_by);

-- Set the FK now that strategy_versions exists
ALTER TABLE strategies
    ADD CONSTRAINT fk_current_version
    FOREIGN KEY (current_version_id) REFERENCES strategy_versions(id) ON DELETE SET NULL;

-- ============================================================
-- RUNS & ORDERS
-- ============================================================

CREATE TABLE strategy_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    strategy_id     UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version_id      UUID REFERENCES strategy_versions(id) ON DELETE SET NULL,
    celery_task_id  TEXT,
    status          TEXT NOT NULL DEFAULT 'queued', -- queued | running | completed | failed | rejected | stopped
    dry_run         BOOLEAN NOT NULL DEFAULT true,
    error           TEXT,
    result          JSONB,
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_runs_strategy ON strategy_runs(strategy_id, created_at DESC);
CREATE INDEX idx_strategy_runs_status   ON strategy_runs(tenant_id, status);
-- Stale-run reaper scans (status='running' AND updated_at < now()-90s) across all
-- tenants; this index makes that a range scan instead of a seq scan.
CREATE INDEX idx_strategy_runs_status_updated ON strategy_runs(status, updated_at);
-- FK index: version_id (REFERENCES strategy_versions ON DELETE SET NULL).
CREATE INDEX idx_strategy_runs_version ON strategy_runs(version_id);

CREATE TABLE orders (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    strategy_id          UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    run_id               UUID REFERENCES strategy_runs(id) ON DELETE SET NULL,
    broker_order_id      TEXT,
    symbol               TEXT NOT NULL,
    exchange             TEXT NOT NULL DEFAULT 'NASDAQ',
    side                 TEXT NOT NULL,           -- buy | sell
    order_type           TEXT NOT NULL,           -- market | limit | stop
    quantity             NUMERIC(18, 8) NOT NULL,
    -- Indian cash equity (NSE/BSE) forbids fractional shares. Enforce whole-share
    -- quantities for those exchanges at the DB layer (defence-in-depth behind
    -- verify_order_intent's Check 3a). US equity / crypto keep fractional support.
    CONSTRAINT chk_orders_whole_shares
        CHECK (exchange NOT IN ('NSE', 'BSE') OR quantity = trunc(quantity)),
    limit_price          NUMERIC(18, 8),
    estimated_price      NUMERIC(18, 8) NOT NULL,
    fill_price           NUMERIC(18, 8),          -- actual fill, populated after execution
    estimated_notional   NUMERIC(18, 8) NOT NULL,
    realized_pnl         NUMERIC(18, 8),          -- populated on position close
    risk_status          TEXT NOT NULL,           -- approved | rejected
    risk_reason          TEXT NOT NULL,
    broker_status        TEXT,                    -- filled | cancelled | rejected | pending
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    filled_at            TIMESTAMPTZ
);
CREATE INDEX idx_orders_strategy    ON orders(strategy_id, created_at DESC);
CREATE INDEX idx_orders_tenant_time ON orders(tenant_id, created_at DESC);
CREATE INDEX idx_orders_symbol      ON orders(symbol, created_at DESC);
-- FK index: run_id (REFERENCES strategy_runs ON DELETE SET NULL).
CREATE INDEX idx_orders_run         ON orders(run_id);

-- ============================================================
-- POSITIONS
-- ============================================================

CREATE TABLE positions (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    strategy_id    UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,
    exchange       TEXT NOT NULL DEFAULT 'NASDAQ',
    quantity       NUMERIC(18, 8) NOT NULL DEFAULT 0,  -- positive = long, negative = short
    -- Whole-share enforcement for NSE/BSE equity (mirrors orders.quantity).
    CONSTRAINT chk_positions_whole_shares
        CHECK (exchange NOT IN ('NSE', 'BSE') OR quantity = trunc(quantity)),
    avg_cost       NUMERIC(18, 8) NOT NULL DEFAULT 0,
    current_price  NUMERIC(18, 8),
    unrealized_pnl NUMERIC(18, 8),
    realized_pnl   NUMERIC(18, 8) NOT NULL DEFAULT 0,
    opened_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, strategy_id, symbol)
);
CREATE INDEX idx_positions_tenant   ON positions(tenant_id);
CREATE INDEX idx_positions_strategy ON positions(strategy_id);

-- ============================================================
-- PORTFOLIO SNAPSHOTS (powers equity curve)
-- ============================================================

CREATE TABLE portfolio_snapshots (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    snapshot_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_equity      NUMERIC(18, 8) NOT NULL,
    cash_balance      NUMERIC(18, 8),
    open_pnl          NUMERIC(18, 8) NOT NULL DEFAULT 0,
    realized_pnl_today NUMERIC(18, 8) NOT NULL DEFAULT 0,
    active_strategies INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_portfolio_snapshots_tenant_time
    ON portfolio_snapshots(tenant_id, snapshot_time DESC);

-- ============================================================
-- BACKTESTING
-- ============================================================

CREATE TABLE backtest_results (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id       UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version_id        UUID REFERENCES strategy_versions(id) ON DELETE SET NULL,
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    symbol            TEXT NOT NULL,
    exchange          TEXT NOT NULL DEFAULT 'NASDAQ',
    timeframe         TEXT NOT NULL,
    start_date        TIMESTAMPTZ NOT NULL,
    end_date          TIMESTAMPTZ NOT NULL,
    initial_capital   NUMERIC(18, 8) NOT NULL DEFAULT 10000,
    final_equity      NUMERIC(18, 8),
    total_return_pct  NUMERIC(10, 4),
    annualized_return_pct NUMERIC(10, 4),
    sharpe_ratio      NUMERIC(10, 4),
    sortino_ratio     NUMERIC(10, 4),
    max_drawdown_pct  NUMERIC(10, 4),
    max_drawdown_start TIMESTAMPTZ,
    max_drawdown_end   TIMESTAMPTZ,
    win_rate_pct      NUMERIC(10, 4),
    profit_factor     NUMERIC(10, 4),
    calmar_ratio      NUMERIC(10, 4),
    total_trades      INT,
    winning_trades    INT,
    losing_trades     INT,
    avg_win           NUMERIC(18, 8),
    avg_loss          NUMERIC(18, 8),
    avg_duration_hours NUMERIC(10, 2),
    equity_curve_json JSONB,  -- [{t: ISO datetime, equity: float}]
    trades_json       JSONB,  -- [{t, symbol, side, qty, price, pnl}]
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_backtest_strategy ON backtest_results(strategy_id, created_at DESC);
-- FK index: version_id (REFERENCES strategy_versions ON DELETE SET NULL).
CREATE INDEX idx_backtest_version  ON backtest_results(version_id);

-- ============================================================
-- MARKET INTELLIGENCE
-- ============================================================

CREATE TABLE market_data_cache (
    symbol    TEXT NOT NULL,
    exchange  TEXT NOT NULL DEFAULT 'NASDAQ',
    timeframe TEXT NOT NULL,
    bar_time  TIMESTAMPTZ NOT NULL,
    open      NUMERIC(18, 4),
    high      NUMERIC(18, 4),
    low       NUMERIC(18, 4),
    close     NUMERIC(18, 4),
    volume    BIGINT,
    PRIMARY KEY (symbol, exchange, timeframe, bar_time)
);
-- NOTE: idx_market_data_symbol_time was removed — it duplicated the PRIMARY KEY
-- btree on (symbol, exchange, timeframe, bar_time). Postgres scans the PK index
-- backward for `ORDER BY bar_time DESC`, so the extra index only cost write IO.

CREATE TABLE news_items (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol       TEXT NOT NULL,
    headline     TEXT NOT NULL,
    summary      TEXT,
    source       TEXT NOT NULL,
    url          TEXT,
    sentiment    TEXT CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    category     TEXT CHECK (category IN ('earnings', 'regulatory', 'political', 'product', 'macro', 'other')),
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_news_symbol_published ON news_items(symbol, published_at DESC);

CREATE TABLE forecasts (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol        TEXT NOT NULL,
    exchange      TEXT NOT NULL DEFAULT 'NASDAQ',
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_days  INT NOT NULL DEFAULT 5,
    model         TEXT NOT NULL,  -- prophet | arima | ensemble
    mae           NUMERIC(18, 4), -- mean absolute error on validation set
    mape          NUMERIC(10, 4), -- mean absolute percentage error
    forecast_json JSONB NOT NULL  -- [{date, yhat, yhat_lower, yhat_upper}]
);
CREATE INDEX idx_forecasts_symbol_generated ON forecasts(symbol, exchange, generated_at DESC);

-- ============================================================
-- NOTIFICATIONS
-- ============================================================

CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL, -- trade_executed | bot_error | pnl_threshold | news | system
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    entity_type TEXT,          -- strategy | run | order
    entity_id   UUID,
    is_read     BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notifications_user    ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX idx_notifications_tenant  ON notifications(tenant_id, created_at DESC);

-- ============================================================
-- AUDIT TRAIL
-- ============================================================

CREATE TABLE audit_events (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id    UUID REFERENCES tenants(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type   TEXT NOT NULL,   -- strategy.created | order.placed | risk.rejected | auth.login ...
    entity_type  TEXT NOT NULL,
    entity_id    UUID,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_tenant_time ON audit_events(tenant_id, created_at DESC);
CREATE INDEX idx_audit_entity      ON audit_events(entity_type, entity_id, created_at DESC);
-- FK index: actor_user_id (REFERENCES users ON DELETE SET NULL).
CREATE INDEX idx_audit_actor       ON audit_events(actor_user_id);

-- ── LLM Configs (BYOAK — Bring Your Own API Key) ─────────────────────────────
-- Users add their own LLM provider keys for NL strategy generation.
-- Falls back to platform-level key (server .env) when none provided.
CREATE TABLE llm_configs (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id        UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_user_id    UUID        NOT NULL REFERENCES users(id),
    label            TEXT        NOT NULL,
    provider         TEXT        NOT NULL DEFAULT 'custom',
    base_url         TEXT        NOT NULL,
    key_encrypted    TEXT        NOT NULL,
    model            TEXT        NOT NULL,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_llm_configs_tenant ON llm_configs(tenant_id, is_active);
-- FK index: owner_user_id (REFERENCES users).
CREATE INDEX idx_llm_configs_owner  ON llm_configs(owner_user_id);

-- ============================================================
-- WEALTH-TECH PIVOT — SIP ADVISOR (Phase 1/2)
-- Foundational tables for the "Investment Advisor for Stock Portfolios & SIPs"
-- model. Equivalent Alembic migration: alembic/versions/xxxx_sip_advisor.py.
-- ============================================================

-- ── User risk profiles (KYC + suitability) ───────────────────────────────────
-- One active profile per user; drives which model portfolios a SIP may use.
-- SEBI suitability requires a risk score + horizon on record before advising.
CREATE TABLE user_risk_profiles (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- KYC
    pan                 TEXT,                      -- Indian Permanent Account Number (store encrypted in app layer)
    kyc_status          TEXT NOT NULL DEFAULT 'pending'   -- pending | verified | rejected
                        CHECK (kyc_status IN ('pending', 'verified', 'rejected')),
    kyc_verified_at     TIMESTAMPTZ,
    date_of_birth       DATE,
    annual_income_band  TEXT,                      -- e.g. '0-5L' | '5-10L' | '10-25L' | '25L+'
    -- Suitability
    risk_tolerance      TEXT NOT NULL DEFAULT 'moderate'  -- conservative | moderate | aggressive
                        CHECK (risk_tolerance IN ('conservative', 'moderate', 'aggressive')),
    risk_score          INT  NOT NULL DEFAULT 50   -- 0 (lowest) .. 100 (highest) from questionnaire
                        CHECK (risk_score BETWEEN 0 AND 100),
    investment_horizon_years INT NOT NULL DEFAULT 5
                        CHECK (investment_horizon_years > 0),
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One active profile per user.
CREATE UNIQUE INDEX idx_user_risk_profiles_active
    ON user_risk_profiles(user_id) WHERE is_active;
CREATE INDEX idx_user_risk_profiles_tenant ON user_risk_profiles(tenant_id);

-- ── Model portfolios (target asset weights / constituents) ────────────────────
-- A curated basket the advisor allocates SIP contributions into. Constituents +
-- target weights live in JSONB so rebalancing the basket is a single versioned row.
CREATE TABLE model_portfolios (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    -- Suitability band this basket is appropriate for (matched against user_risk_profiles).
    risk_band           TEXT NOT NULL DEFAULT 'moderate'
                        CHECK (risk_band IN ('conservative', 'moderate', 'aggressive')),
    currency            TEXT NOT NULL DEFAULT 'INR',
    exchange            TEXT NOT NULL DEFAULT 'NSE',
    -- [{symbol, exchange, target_weight}], target_weight as fraction summing to ~1.0.
    -- Enforced in the app layer (weights sum, symbol validity); stored as JSONB here.
    constituents        JSONB NOT NULL DEFAULT '[]'::jsonb,
    version             INT  NOT NULL DEFAULT 1,    -- bumped on every rebalance
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name, version)
);
CREATE INDEX idx_model_portfolios_tenant ON model_portfolios(tenant_id, is_active);
CREATE INDEX idx_model_portfolios_band   ON model_portfolios(risk_band) WHERE is_active;

-- ── User Mandates (e-NACH / UPI AutoPay master limits) ────────────────────────
CREATE TABLE user_mandates (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mandate_ref         VARCHAR(255) UNIQUE NOT NULL,
    max_amount          NUMERIC(18, 2) NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'revoked', 'expired')),
    expiry_date         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_mandates_tenant ON user_mandates(tenant_id, status);
CREATE INDEX idx_user_mandates_user ON user_mandates(user_id);
CREATE INDEX idx_user_mandates_expiry ON user_mandates(expiry_date);

-- ── SIP mandates (recurring auto-invest instructions) ─────────────────────────
-- Monthly contribution mapped to a model portfolio, executed on a chosen calendar
-- day, gated by an auto-pay (e-NACH/UPI AutoPay) mandate.
CREATE TABLE sip_mandates (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_portfolio_id  UUID NOT NULL REFERENCES model_portfolios(id) ON DELETE RESTRICT,
    risk_profile_id     UUID REFERENCES user_risk_profiles(id) ON DELETE RESTRICT,
    mandate_id          UUID REFERENCES user_mandates(id) ON DELETE RESTRICT,
    -- Contribution
    amount              NUMERIC(18, 2) NOT NULL CHECK (amount > 0),  -- INR, 2dp (no fractional paise)
    rollover_cash       NUMERIC(18, 2) DEFAULT 0.0 CHECK (rollover_cash >= 0.0),
    currency            TEXT NOT NULL DEFAULT 'INR',
    frequency           TEXT NOT NULL DEFAULT 'monthly'
                        CHECK (frequency IN ('weekly', 'monthly', 'quarterly')),
    execution_day       INT  NOT NULL DEFAULT 1       -- day-of-month (1..28 keeps it valid every month)
                        CHECK (execution_day BETWEEN 1 AND 28),
    -- Auto-pay mandate (e-NACH / UPI AutoPay) lifecycle
    autopay_status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (autopay_status IN ('pending', 'active', 'paused', 'cancelled', 'failed')),
    -- Scheduling
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'cancelled')),
    start_date          DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date            DATE,                        -- NULL = open-ended
    next_execution_date DATE,
    last_executed_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sip_mandates_user   ON sip_mandates(user_id);
CREATE INDEX idx_sip_mandates_tenant ON sip_mandates(tenant_id, status);
-- FK indexes for the references without a covering index.
CREATE INDEX idx_sip_mandates_portfolio ON sip_mandates(model_portfolio_id);
CREATE INDEX idx_sip_mandates_risk_profile ON sip_mandates(risk_profile_id);
CREATE INDEX idx_sip_mandates_mandate ON sip_mandates(mandate_id);
-- Daily scheduler scans for due mandates: (status='active' AND next_execution_date <= today).
CREATE INDEX idx_sip_mandates_due
    ON sip_mandates(next_execution_date) WHERE status = 'active';
