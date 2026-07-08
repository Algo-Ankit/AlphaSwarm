"""Email verification flag.

Password-reset tokens are stateless signed JWTs (no table needed) — they embed
a fingerprint of the current password hash so they self-invalidate the moment
the password changes. Email verification only needs a boolean on the user.

Broker-identity accounts (Upstox) arrive with a KYC-verified email, so they
are backfilled as verified.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false"
    )
    # Broker OAuth identities carry a KYC-verified email — trust it.
    op.execute("UPDATE users SET email_verified = true WHERE auth_provider <> 'password'")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
