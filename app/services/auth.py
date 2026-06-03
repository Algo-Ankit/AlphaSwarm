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
