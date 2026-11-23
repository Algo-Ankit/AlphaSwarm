"""Broker-identity login ("Continue with Upstox").

Users created through a broker OAuth flow have no password — the broker's
KYC-verified account IS the identity. password_hash becomes nullable and
auth_provider records how the account authenticates ('password' | 'upstox').

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'password'"
    )
    # A passwordless row must say which provider owns the identity.
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE users ADD CONSTRAINT users_auth_provider_check
            CHECK (password_hash IS NOT NULL OR auth_provider <> 'password');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_auth_provider_check")
    # Broker-login rows have no hash; backfill an unusable sentinel before
    # restoring NOT NULL (bcrypt will never verify against this value).
    op.execute("UPDATE users SET password_hash = '!broker-login' WHERE password_hash IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth_provider")
