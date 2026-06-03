import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _sign_key() -> tuple[str, str]:
    settings = get_settings()
    if settings.jwt_private_key:
        return settings.jwt_private_key, "RS256"
    return settings.jwt_secret_key, "HS256"


def _verify_key() -> tuple[str, str]:
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
        payload = jwt.decode(token, key, algorithms=[algorithm])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def get_refresh_token_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
