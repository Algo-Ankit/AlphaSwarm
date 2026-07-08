import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings

# --------------------------------------------------------------------------- #
# Password hashing — raw bcrypt, no passlib wrapper                           #
# passlib is unmaintained and throws deprecation crashes on modern bcrypt      #
# --------------------------------------------------------------------------- #


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# Pre-computed hash used to equalize login timing when the email does not exist.
# Without this, a missing-user login returns ~instantly while a wrong-password
# login takes a full bcrypt verify — a timing oracle for email enumeration.
_TIMING_EQUALIZER_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode()


def equalize_login_timing(plain: str) -> None:
    """Burn one bcrypt verify so unknown-email and wrong-password take equal time."""
    bcrypt.checkpw(plain.encode(), _TIMING_EQUALIZER_HASH.encode())


# --------------------------------------------------------------------------- #
# JWT — PyJWT, not python-jose                                                 #
# python-jose is abandoned and has CVE-2022-29217 (algorithm confusion)       #
# PyJWT is actively maintained and correctly refuses alg=none attacks          #
# --------------------------------------------------------------------------- #


def _sign_key() -> tuple[str | bytes, str]:
    settings = get_settings()
    if settings.jwt_private_key:
        return settings.jwt_private_key, "RS256"
    return settings.jwt_secret_key, "HS256"


def _verify_key() -> tuple[str | bytes, str]:
    settings = get_settings()
    if settings.jwt_public_key:
        return settings.jwt_public_key, "RS256"
    return settings.jwt_secret_key, "HS256"


def create_access_token(user_id: str, tenant_id: str, email: str, role: str) -> str:
    settings = get_settings()
    key, algorithm = _sign_key()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def decode_access_token(token: str) -> dict | None:
    key, algorithm = _verify_key()
    try:
        # algorithms= kwarg forces PyJWT to reject algorithm confusion —
        # it will not accept a token signed with any algorithm not in this list
        payload = jwt.decode(token, key, algorithms=[algorithm])
        if payload.get("type") != "access":
            return None
        return payload
    except InvalidTokenError:
        return None


# --------------------------------------------------------------------------- #
# OAuth state tokens — stateless CSRF protection for pre-auth broker login     #
# --------------------------------------------------------------------------- #
# The "Continue with Upstox" flow starts BEFORE any user session exists, so the
# state can't be stored against a tenant row (unlike the broker-connect flow).
# Instead the state is a short-lived signed JWT: the callback verifies the
# signature and expiry, proving WE minted it minutes ago for this purpose.


def create_state_token(purpose: str, ttl_seconds: int = 600) -> str:
    key, algorithm = _sign_key()
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": purpose,
        "nonce": secrets.token_urlsafe(16),
        "type": "oauth_state",
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def verify_state_token(token: str, purpose: str) -> bool:
    key, algorithm = _verify_key()
    try:
        payload = jwt.decode(token, key, algorithms=[algorithm])
    except InvalidTokenError:
        return False
    return payload.get("type") == "oauth_state" and payload.get("purpose") == purpose


# --------------------------------------------------------------------------- #
# Refresh tokens                                                               #
# --------------------------------------------------------------------------- #


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def get_refresh_token_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)


def get_grace_period_expiry() -> datetime:
    """
    Used for refresh token rotation race condition.
    When a token is rotated, the old token stays valid in Redis for this window
    so concurrent requests (e.g. two browser tabs refreshing simultaneously)
    don't trigger a false-positive token theft alarm.
    """
    return datetime.now(timezone.utc) + timedelta(seconds=45)
