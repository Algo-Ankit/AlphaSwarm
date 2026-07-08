"""Feed likes + honest Swarm Tax states.

- social_post_likes: one row per (post, tenant) — powers the Like button and
  makes likes_count auditable instead of a write-only counter.
- fee_status gains 'invoiced': a Razorpay order was issued but not yet paid.
  (order.create does not collect money; 'charged' must mean money in hand.)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── social_post_likes ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_post_likes (
            post_id     UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (post_id, tenant_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_post_likes_tenant ON social_post_likes(tenant_id)"
    )

    # ── fee_status: allow 'invoiced' ─────────────────────────────────────────
    op.execute(
        "ALTER TABLE strategy_subscriptions DROP CONSTRAINT IF EXISTS strategy_subscriptions_fee_status_check"
    )
    op.execute("""
        ALTER TABLE strategy_subscriptions
            ADD CONSTRAINT strategy_subscriptions_fee_status_check
            CHECK (fee_status IN ('unpaid', 'charged', 'invoiced', 'failed', 'exempt'))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_post_likes")
    op.execute(
        "ALTER TABLE strategy_subscriptions DROP CONSTRAINT IF EXISTS strategy_subscriptions_fee_status_check"
    )
    op.execute("UPDATE strategy_subscriptions SET fee_status = 'unpaid' WHERE fee_status = 'invoiced'")
    op.execute("""
        ALTER TABLE strategy_subscriptions
            ADD CONSTRAINT strategy_subscriptions_fee_status_check
            CHECK (fee_status IN ('unpaid', 'charged', 'failed', 'exempt'))
    """)
