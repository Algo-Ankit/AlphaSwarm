"""Strategy Commons: immutable published versions + fork lineage graph.

Turns the flat leaderboard into a GitHub-style commons:

- A listing pins the EXACT immutable strategy_version it published
  (published_version_id) rather than tracking the creator's mutable head — what
  people fork is a frozen snapshot, not an editable post.
- Every listing records the listing it was forked from
  (forked_from_public_strategy_id) and a denormalized fork_count, so the whole
  lineage — "the strategy 400 people forked, and the 12 mutations that beat it"
  — is a walk over the graph.
- A private strategy remembers the listing it was forked from
  (strategies.forked_from_public_strategy_id) so the lineage link survives until
  the fork is itself published.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Private strategy → the public listing it was forked from (if any).
    op.execute(
        "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS forked_from_public_strategy_id "
        "UUID REFERENCES public_strategies(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategies_forked_from "
        "ON strategies(forked_from_public_strategy_id) "
        "WHERE forked_from_public_strategy_id IS NOT NULL"
    )

    # Listing pins the exact immutable version it published.
    op.execute(
        "ALTER TABLE public_strategies ADD COLUMN IF NOT EXISTS published_version_id "
        "UUID REFERENCES strategy_versions(id) ON DELETE SET NULL"
    )
    # Lineage: the listing this one descends from + a denormalized child count.
    op.execute(
        "ALTER TABLE public_strategies ADD COLUMN IF NOT EXISTS forked_from_public_strategy_id "
        "UUID REFERENCES public_strategies(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE public_strategies ADD COLUMN IF NOT EXISTS fork_count "
        "INT NOT NULL DEFAULT 0 CHECK (fork_count >= 0)"
    )
    op.execute(
        "ALTER TABLE public_strategies ADD COLUMN IF NOT EXISTS published_at "
        "TIMESTAMPTZ NOT NULL DEFAULT now()"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_public_strategies_forked_from "
        "ON public_strategies(forked_from_public_strategy_id) "
        "WHERE forked_from_public_strategy_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_public_strategies_forked_from")
    op.execute("ALTER TABLE public_strategies DROP COLUMN IF EXISTS published_at")
    op.execute("ALTER TABLE public_strategies DROP COLUMN IF EXISTS fork_count")
    op.execute(
        "ALTER TABLE public_strategies DROP COLUMN IF EXISTS forked_from_public_strategy_id"
    )
    op.execute("ALTER TABLE public_strategies DROP COLUMN IF EXISTS published_version_id")
    op.execute("DROP INDEX IF EXISTS idx_strategies_forked_from")
    op.execute("ALTER TABLE strategies DROP COLUMN IF EXISTS forked_from_public_strategy_id")
