from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _user_or_ip(request: Request) -> str:
    """Rate-limit key: JWT user ID when available, falls back to client IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        from app.services.auth import decode_access_token
        payload = decode_access_token(auth[7:])
        if payload and "sub" in payload:
            return f"user:{payload['sub']}"
    return get_remote_address(request)


limiter = Limiter(key_func=_user_or_ip)
