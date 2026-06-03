"""Initial schema — all tables from schema.sql

Revision ID: 0001
Revises:
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name       TEXT NOT NULL,
            plan       TEXT NOT NULL DEFAULT 'founding_member',
            max_bots   INT  NOT NULL DEFAULT 5,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email         TEXT NOT NULL,
            display_name  TEXT,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'member',
            is_active     BOOLEAN NOT NULL DEFAULT true,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, email)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash      TEXT NOT NULL UNIQUE,
            expires_at      TIMESTAMPTZ NOT NULL,
            grace_period_until TIMESTAMPTZ,
            rotated_to_hash TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS broker_connections (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            broker           TEXT NOT NULL DEFAULT 'alpaca',
            key_encrypted    TEXT NOT NULL,
            secret_encrypted TEXT NOT NULL,
            base_url         TEXT,
            is_paper         BOOLEAN NOT NULL DEFAULT true,
            is_active        BOOLEAN NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, broker)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            owner_user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name               TEXT NOT NULL,
            description        TEXT,
            symbols            TEXT[] NOT NULL DEFAULT ARRAY['SPY'],
            exchange           TEXT NOT NULL DEFAULT 'NASDAQ',
            timeframe          TEXT NOT NULL DEFAULT '1d',
            status             TEXT NOT NULL DEFAULT 'draft',
            creation_mode      TEXT NOT NULL DEFAULT 'nl',
            prompt             TEXT NOT NULL DEFAULT '',
            risk_config        JSONB NOT NULL DEFAULT '{}'::jsonb,
            current_version_id UUID,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategies_tenant_status ON strategies(tenant_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS strategy_versions (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id     UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            version_number  INT  NOT NULL DEFAULT 1,
            generated_logic TEXT NOT NULL,
            prompt_snapshot TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by      UUID REFERENCES users(id),
            UNIQUE (strategy_id, version_number)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy ON strategy_versions(strategy_id, version_number DESC)")

    # Wrap in DO block so the migration is idempotent on DBs pre-seeded from schema.sql
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_current_version'
                  AND table_name = 'strategies'
            ) THEN
                ALTER TABLE strategies
                    ADD CONSTRAINT fk_current_version
                    FOREIGN KEY (current_version_id)
                    REFERENCES strategy_versions(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS strategy_runs (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            strategy_id    UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            version_id     UUID REFERENCES strategy_versions(id) ON DELETE SET NULL,
            celery_task_id TEXT,
            status         TEXT NOT NULL DEFAULT 'queued',
            dry_run        BOOLEAN NOT NULL DEFAULT true,
            error          TEXT,
            result         JSONB,
            started_at     TIMESTAMPTZ,
            ended_at       TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_runs_strategy ON strategy_runs(strategy_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_runs_status ON strategy_runs(tenant_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            strategy_id        UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            run_id             UUID REFERENCES strategy_runs(id) ON DELETE SET NULL,
            broker_order_id    TEXT,
            symbol             TEXT NOT NULL,
            exchange           TEXT NOT NULL DEFAULT 'NASDAQ',
            side               TEXT NOT NULL,
            order_type         TEXT NOT NULL,
            quantity           NUMERIC(18, 8) NOT NULL,
            limit_price        NUMERIC(18, 8),
            estimated_price    NUMERIC(18, 8) NOT NULL,
            fill_price         NUMERIC(18, 8),
            estimated_notional NUMERIC(18, 8) NOT NULL,
            realized_pnl       NUMERIC(18, 8),
            risk_status        TEXT NOT NULL,
            risk_reason        TEXT NOT NULL,
            broker_status      TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            filled_at          TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders(strategy_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_tenant_time ON orders(tenant_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            strategy_id    UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            symbol         TEXT NOT NULL,
            exchange       TEXT NOT NULL DEFAULT 'NASDAQ',
            quantity       NUMERIC(18, 8) NOT NULL DEFAULT 0,
            avg_cost       NUMERIC(18, 8) NOT NULL DEFAULT 0,
            current_price  NUMERIC(18, 8),
            unrealized_pnl NUMERIC(18, 8),
            realized_pnl   NUMERIC(18, 8) NOT NULL DEFAULT 0,
            opened_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, strategy_id, symbol)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_tenant ON positions(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            snapshot_time       TIMESTAMPTZ NOT NULL DEFAULT now(),
            total_equity        NUMERIC(18, 8) NOT NULL,
            cash_balance        NUMERIC(18, 8),
            open_pnl            NUMERIC(18, 8) NOT NULL DEFAULT 0,
            realized_pnl_today  NUMERIC(18, 8) NOT NULL DEFAULT 0,
            active_strategies   INT NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_tenant_time ON portfolio_snapshots(tenant_id, snapshot_time DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id           UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            version_id            UUID REFERENCES strategy_versions(id) ON DELETE SET NULL,
            tenant_id             UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            symbol                TEXT NOT NULL,
            exchange              TEXT NOT NULL DEFAULT 'NASDAQ',
            timeframe             TEXT NOT NULL,
            start_date            TIMESTAMPTZ NOT NULL,
            end_date              TIMESTAMPTZ NOT NULL,
            initial_capital       NUMERIC(18, 8) NOT NULL DEFAULT 10000,
            final_equity          NUMERIC(18, 8),
            total_return_pct      NUMERIC(10, 4),
            annualized_return_pct NUMERIC(10, 4),
            sharpe_ratio          NUMERIC(10, 4),
            sortino_ratio         NUMERIC(10, 4),
            max_drawdown_pct      NUMERIC(10, 4),
            max_drawdown_start    TIMESTAMPTZ,
            max_drawdown_end      TIMESTAMPTZ,
            win_rate_pct          NUMERIC(10, 4),
            profit_factor         NUMERIC(10, 4),
            total_trades          INT,
            winning_trades        INT,
            losing_trades         INT,
            avg_win               NUMERIC(18, 8),
            avg_loss              NUMERIC(18, 8),
            avg_duration_hours    NUMERIC(10, 2),
            equity_curve_json     JSONB,
            trades_json           JSONB,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS market_data_cache (
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_data_symbol_time ON market_data_cache(symbol, exchange, timeframe, bar_time DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
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
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_news_symbol_published ON news_items(symbol, published_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS forecasts (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            symbol        TEXT NOT NULL,
            exchange      TEXT NOT NULL DEFAULT 'NASDAQ',
            generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            horizon_days  INT NOT NULL DEFAULT 5,
            model         TEXT NOT NULL,
            mae           NUMERIC(18, 4),
            mape          NUMERIC(10, 4),
            forecast_json JSONB NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_symbol_generated ON forecasts(symbol, exchange, generated_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
            type        TEXT NOT NULL,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL,
            entity_type TEXT,
            entity_id   UUID,
            is_read     BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON notifications(tenant_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE,
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            event_type    TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            entity_id     UUID,
            payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_events(tenant_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id, created_at DESC)")


def downgrade() -> None:
    for table in [
        "audit_events", "notifications", "forecasts", "news_items",
        "market_data_cache", "backtest_results", "portfolio_snapshots",
        "positions", "orders", "strategy_runs", "strategy_versions",
        "strategies", "broker_connections", "refresh_tokens", "users", "tenants",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
