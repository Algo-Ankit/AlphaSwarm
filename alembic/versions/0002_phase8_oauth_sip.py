"""Phase 8: broker OAuth tokens + strategy SIP controls

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Broker OAuth token storage (nullable — API-key brokers don't use these)
    op.execute("""
        ALTER TABLE broker_connections
            ADD COLUMN IF NOT EXISTS oauth_state      TEXT,
            ADD COLUMN IF NOT EXISTS access_token     TEXT,
            ADD COLUMN IF NOT EXISTS refresh_token    TEXT,
            ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ
    """)

    # Strategy SIP controls
    op.execute("""
        ALTER TABLE strategies
            ADD COLUMN IF NOT EXISTS sip_paused         BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS sip_monthly_amount NUMERIC(18, 8),
            ADD COLUMN IF NOT EXISTS sip_frequency      TEXT    NOT NULL DEFAULT 'monthly'
    """)

    # Rebalance-approval support: add approved_at to notifications
    op.execute("""
        ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE broker_connections
            DROP COLUMN IF EXISTS oauth_state,
            DROP COLUMN IF EXISTS access_token,
            DROP COLUMN IF EXISTS refresh_token,
            DROP COLUMN IF EXISTS token_expires_at
    """)
    op.execute("""
        ALTER TABLE strategies
            DROP COLUMN IF EXISTS sip_paused,
            DROP COLUMN IF EXISTS sip_monthly_amount,
            DROP COLUMN IF EXISTS sip_frequency
    """)
    op.execute("""
        ALTER TABLE notifications
            DROP COLUMN IF EXISTS approved_at
    """)
