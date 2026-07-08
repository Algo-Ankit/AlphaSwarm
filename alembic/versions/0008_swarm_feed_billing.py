"""Swarm Feed + Billing: social_posts, creator_balances, billing columns on strategy_subscriptions

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── social_posts ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            public_strategy_id  UUID REFERENCES public_strategies(id) ON DELETE SET NULL,
            content_markdown    TEXT NOT NULL
                                CHECK (char_length(content_markdown) BETWEEN 1 AND 5000),
            likes_count         INT NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_posts_tenant   ON social_posts(tenant_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_posts_strategy ON social_posts(public_strategy_id) WHERE public_strategy_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_social_posts_timeline ON social_posts(created_at DESC)"
    )

    # ── strategy_subscriptions — add Swarm Tax billing columns ───────────────
    op.execute("""
        ALTER TABLE strategy_subscriptions
            ADD COLUMN IF NOT EXISTS last_billed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS fee_status TEXT NOT NULL DEFAULT 'unpaid'
                CHECK (fee_status IN ('unpaid', 'charged', 'failed', 'exempt'))
    """)

    # ── creator_balances — revenue ledger (platform 50% / creator 50%) ───────
    op.execute("""
        CREATE TABLE IF NOT EXISTS creator_balances (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            creator_tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            subscription_id     UUID REFERENCES strategy_subscriptions(id) ON DELETE SET NULL,
            amount              NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
            currency            TEXT NOT NULL DEFAULT 'USD',
            credit_type         TEXT NOT NULL DEFAULT 'creator_share'
                                CHECK (credit_type IN ('creator_share', 'platform_share')),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_creator_balances_tenant ON creator_balances(creator_tenant_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS creator_balances")
    op.execute("DROP TABLE IF EXISTS social_posts")
    op.execute("ALTER TABLE strategy_subscriptions DROP COLUMN IF EXISTS last_billed_at")
    op.execute("ALTER TABLE strategy_subscriptions DROP COLUMN IF EXISTS fee_status")
