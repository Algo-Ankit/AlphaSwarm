"""Social copy trading: public_strategies + strategy_subscriptions

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A creator publishes one of their private strategies to the public "Swarm"
    # leaderboard. UNIQUE(strategy_id) means a strategy is listed at most once.
    # management_fee_bps is informational (the platform holds no funds and settles
    # no fees) — copied orders execute in each subscriber's OWN broker account.
    op.execute("""
        CREATE TABLE IF NOT EXISTS public_strategies (
            id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            strategy_id        UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            creator_tenant_id  UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            creator_user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
            title              TEXT NOT NULL,
            description        TEXT NOT NULL DEFAULT '',
            management_fee_bps INT  NOT NULL DEFAULT 0 CHECK (management_fee_bps BETWEEN 0 AND 10000),
            subscriber_count   INT  NOT NULL DEFAULT 0 CHECK (subscriber_count >= 0),
            is_verified        BOOLEAN NOT NULL DEFAULT false,
            is_listed          BOOLEAN NOT NULL DEFAULT true,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (strategy_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_public_strategies_creator ON public_strategies(creator_tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_public_strategies_listed ON public_strategies(is_listed) WHERE is_listed")

    # A subscriber (tenant) copies a published strategy, dedicating allocated_capital
    # to it. The execution engine fans signals out to every active subscription,
    # sizing each copied order proportionally to allocated_capital. One subscription
    # per (public_strategy, subscriber tenant).
    op.execute("""
        CREATE TABLE IF NOT EXISTS strategy_subscriptions (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            public_strategy_id   UUID NOT NULL REFERENCES public_strategies(id) ON DELETE CASCADE,
            subscriber_tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            subscriber_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
            allocated_capital    NUMERIC(18, 2) NOT NULL CHECK (allocated_capital > 0),
            is_active            BOOLEAN NOT NULL DEFAULT true,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (public_strategy_id, subscriber_tenant_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_subscriptions_public ON strategy_subscriptions(public_strategy_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_strategy_subscriptions_subscriber ON strategy_subscriptions(subscriber_tenant_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS strategy_subscriptions")
    op.execute("DROP TABLE IF EXISTS public_strategies")
