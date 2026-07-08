"""Strategy Commons: out-of-sample honesty columns.

Guards against survivorship-bias theater. Every listing carries an
out-of-sample scorecard — a backtest of the pinned version over data AFTER its
publish date (oos_start_date), recomputed periodically. Displaying decayed
alpha honestly next to the in-sample numbers is the whole point: a strategy
that only looked good on the data it was tuned on is exposed, not hidden.

The publish gate itself (a minimum number of on-platform backtest runs) is
enforced in application code, not schema.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col, ddl in (
        ("oos_start_date", "TIMESTAMPTZ"),
        ("oos_total_return_pct", "NUMERIC(10, 4)"),
        ("oos_annualized_return_pct", "NUMERIC(10, 4)"),
        ("oos_sharpe_ratio", "NUMERIC(10, 4)"),
        ("oos_max_drawdown_pct", "NUMERIC(10, 4)"),
        ("oos_total_trades", "INT"),
        ("oos_computed_at", "TIMESTAMPTZ"),
    ):
        op.execute(f"ALTER TABLE public_strategies ADD COLUMN IF NOT EXISTS {col} {ddl}")


def downgrade() -> None:
    for col in (
        "oos_computed_at",
        "oos_total_trades",
        "oos_max_drawdown_pct",
        "oos_sharpe_ratio",
        "oos_annualized_return_pct",
        "oos_total_return_pct",
        "oos_start_date",
    ):
        op.execute(f"ALTER TABLE public_strategies DROP COLUMN IF EXISTS {col}")
