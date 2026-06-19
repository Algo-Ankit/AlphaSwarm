"""Unified portfolio: multi-broker holdings ingested from a CAS statement

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Consolidated multi-broker holdings parsed from an NSDL/CDSL Consolidated
    # Account Statement. The platform never holds funds — these rows are a
    # read-only display aggregate of the user's externally-custodied assets.
    op.execute("""
        CREATE TABLE IF NOT EXISTS unified_holdings (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            isin          TEXT,
            symbol        TEXT NOT NULL,
            name          TEXT NOT NULL,
            asset_class   TEXT NOT NULL DEFAULT 'equity',  -- equity | mutual_fund | etf | bond | other
            broker        TEXT NOT NULL,                    -- depository participant / broker
            quantity      NUMERIC(20, 8) NOT NULL,
            avg_cost      NUMERIC(20, 8) NOT NULL DEFAULT 0,
            current_price NUMERIC(20, 8),
            current_value NUMERIC(20, 8) NOT NULL DEFAULT 0,
            statement_date DATE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_unified_holdings_tenant
            ON unified_holdings(tenant_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_unified_holdings_tenant")
    op.execute("DROP TABLE IF EXISTS unified_holdings")
