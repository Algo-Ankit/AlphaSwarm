"""GTM pivot: replace Stripe subscription columns with Razorpay

Stripe is RBI-restricted for recurring INR mandates, so billing moves to
Razorpay (UPI AutoPay / e-mandate). Swaps the customer/subscription id columns;
the generic subscription_status / subscription_current_period_end columns stay.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tenants_stripe_customer")
    op.execute(
        """
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS stripe_customer_id,
            DROP COLUMN IF EXISTS stripe_subscription_id,
            ADD COLUMN IF NOT EXISTS razorpay_customer_id     TEXT,
            ADD COLUMN IF NOT EXISTS razorpay_subscription_id TEXT
    """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenants_razorpay_customer ON tenants(razorpay_customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenants_razorpay_subscription "
        "ON tenants(razorpay_subscription_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tenants_razorpay_customer")
    op.execute("DROP INDEX IF EXISTS idx_tenants_razorpay_subscription")
    op.execute(
        """
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS razorpay_customer_id,
            DROP COLUMN IF EXISTS razorpay_subscription_id,
            ADD COLUMN IF NOT EXISTS stripe_customer_id     TEXT,
            ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT
    """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer ON tenants(stripe_customer_id)"
    )
