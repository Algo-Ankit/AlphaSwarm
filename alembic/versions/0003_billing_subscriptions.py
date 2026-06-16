"""GTM: Stripe subscription columns on tenants

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stripe billing state on tenants. subscription_status gates live deployment;
    # anything other than 'active'/'trialing' keeps the tenant paper-only.
    op.execute("""
        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS stripe_customer_id              TEXT,
            ADD COLUMN IF NOT EXISTS stripe_subscription_id          TEXT,
            ADD COLUMN IF NOT EXISTS subscription_status             TEXT NOT NULL DEFAULT 'inactive',
            ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMPTZ
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer "
        "ON tenants(stripe_customer_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tenants_stripe_customer")
    op.execute("""
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS stripe_customer_id,
            DROP COLUMN IF EXISTS stripe_subscription_id,
            DROP COLUMN IF EXISTS subscription_status,
            DROP COLUMN IF EXISTS subscription_current_period_end
    """)
