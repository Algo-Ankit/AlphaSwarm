"""Passwordless OTP login (email or phone).

Adds an optional `phone` identity to users (E.164, unique when present) and a
short-lived `login_otps` table holding only a SHA-256 hash of each 6-digit
code — never the code itself. A code is single-use (consumed_at) and capped at
a few verify attempts before it is dead, so brute-forcing a 6-digit code inside
its 10-minute window is not feasible.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT")
    # Unique only among rows that actually have a phone (partial index).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone "
        "ON users (phone) WHERE phone IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS login_otps (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            identifier  TEXT NOT NULL,        -- normalized email or E.164 phone
            channel     TEXT NOT NULL,        -- 'email' | 'sms'
            code_hash   TEXT NOT NULL,        -- sha256(code) — never the code
            expires_at  TIMESTAMPTZ NOT NULL,
            attempts    INT NOT NULL DEFAULT 0,
            consumed_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_login_otps_identifier "
        "ON login_otps (identifier, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS login_otps")
    op.execute("DROP INDEX IF EXISTS ix_users_phone")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone")
