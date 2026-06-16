"""GTM: dual-gateway billing — restore Stripe columns alongside Razorpay

Migration 0004 dropped the Stripe columns when we pivoted to Razorpay. We now run
BOTH gateways side-by-side (Stripe = USD/Global, Razorpay = INR/India), so the
tenants table needs both sets of customer/subscription id columns. The universal
subscription_status / subscription_current_period_end columns are unchanged.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Re-add Stripe columns (Razorpay columns already present from 0004).
    op.execute(
        """
        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS stripe_customer_id     TEXT,
            ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT
    """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer ON tenants(stripe_customer_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tenants_stripe_customer")
    op.execute(
        """
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS stripe_customer_id,
            DROP COLUMN IF EXISTS stripe_subscription_id
    """
    )
