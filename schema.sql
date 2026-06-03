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
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    key_encrypted    TEXT NOT NULL,    -- Fernet-encrypted API key
    secret_encrypted TEXT NOT NULL,   -- Fernet-encrypted API secret
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

CREATE TABLE strategy_versions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id     UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    version_number  INT  NOT NULL DEFAULT 1,
    generated_logic TEXT NOT NULL,   -- The actual Python code. IMMUTABLE after insert.
    prompt_snapshot TEXT NOT NULL DEFAULT '', -- NL prompt at time of this version
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID REFERENCES users(id),
    UNIQUE (strategy_id, version_number)
);
CREATE INDEX idx_strategy_versions_strategy ON strategy_versions(strategy_id, version_number DESC);

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
CREATE INDEX idx_market_data_symbol_time
    ON market_data_cache(symbol, exchange, timeframe, bar_time DESC);

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
