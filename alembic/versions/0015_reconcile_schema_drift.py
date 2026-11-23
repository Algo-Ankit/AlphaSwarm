"""Reconcile schema drift: llm_configs, strategy_versions.explanation, backtest_results.calmar_ratio.

Ensures a clean database provisioned solely via `alembic upgrade head` has the
exact same tables and columns as `schema.sql`.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE strategy_versions ADD COLUMN IF NOT EXISTS explanation TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS calmar_ratio NUMERIC(10, 4)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_configs (
            id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            owner_user_id UUID        NOT NULL REFERENCES users(id),
            label         TEXT        NOT NULL,
            provider      TEXT        NOT NULL DEFAULT 'custom',
            base_url      TEXT        NOT NULL,
            key_encrypted TEXT        NOT NULL,
            model         TEXT        NOT NULL,
            is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_configs_tenant ON llm_configs(tenant_id, is_active)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_configs_owner ON llm_configs(owner_user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_configs")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS calmar_ratio")
    op.execute("ALTER TABLE strategy_versions DROP COLUMN IF EXISTS explanation")
