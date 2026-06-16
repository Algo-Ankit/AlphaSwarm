import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.config import get_settings
from app.db.repositories.brokers import BrokerRepo
from app.services.broker_crypto import decrypt_key, encrypt_key
from app.services import oauth_manager as oauth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/brokers", tags=["brokers"])

_ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
_ALPACA_LIVE_URL  = "https://api.alpaca.markets"

# Brokers that use OAuth redirect flows
_OAUTH_REDIRECT_BROKERS = {"upstox", "zerodha"}
# Brokers that use credential-based API login (no OAuth redirect)
_OAUTH_CREDENTIAL_BROKERS = {"angelone"}


def _validate_url(url: str, broker: str) -> None:
    if not url:
        return
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid base_url for {broker}: must be a valid http/https URL",
        )


def _oauth_redirect_uri(broker: str) -> str:
    settings = get_settings()
    base = getattr(settings, "app_base_url", "http://localhost:3000").rstrip("/")
    return f"{base}/settings/brokers/oauth/callback"


# ── Pydantic models ────────────────────────────────────────────────────────────

class BrokerConnectRequest(BaseModel):
    broker: str = Field(default="alpaca", pattern="^(alpaca|upstox|zerodha|angelone)$")
    api_key: str = Field(min_length=1, max_length=256)
    api_secret: str = Field(min_length=1, max_length=256)
    is_paper: bool = True
    base_url: str | None = None


class BrokerConnectionResponse(BaseModel):
    id: str
    broker: str
    base_url: str | None
    is_paper: bool
    is_active: bool
    key_preview: str
    oauth_connected: bool
    token_status: str       # 'connected' | 'expired' | 'none'
    token_expires_at: str | None
    created_at: str
    updated_at: str


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    account_id: str | None = None


class OAuthLoginUrlResponse(BaseModel):
    login_url: str
    state: str | None = None


class OAuthCallbackRequest(BaseModel):
    code: str | None = None
    request_token: str | None = None  # Zerodha uses request_token instead of code
    state: str | None = None
    broker: str = Field(pattern="^(upstox|zerodha)$")


class AngelOneLoginRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp: str = Field(min_length=6, max_length=8)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _token_status(row: asyncpg.Record) -> str:
    access_token = row.get("access_token")
    if not access_token:
        return "none"
    expires_at = row.get("token_expires_at")
    if expires_at:
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                return "expired"
    return "connected"


async def _test_alpaca(api_key: str, api_secret: str, base_url: str) -> TestConnectionResponse:
    url = f"{base_url.rstrip('/')}/v2/account"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            })
        if resp.status_code == 200:
            data = resp.json()
            acct_id = data.get("account_number") or data.get("id")
            acct_status = data.get("status")
            if acct_status and acct_status != "ACTIVE":
                return TestConnectionResponse(ok=False, message=f"Alpaca account is not active (status: {acct_status})")
            return TestConnectionResponse(ok=True, message="Connected successfully", account_id=acct_id)
        if resp.status_code in (401, 403):
            return TestConnectionResponse(ok=False, message="Invalid API key or secret")
        return TestConnectionResponse(ok=False, message=f"Alpaca returned HTTP {resp.status_code}")
    except httpx.TimeoutException:
        return TestConnectionResponse(ok=False, message="Connection timed out — check the base URL")
    except httpx.RequestError as exc:
        return TestConnectionResponse(ok=False, message=f"Network error: {exc}")
    except Exception:
        logger.exception("Unexpected error in Alpaca connection test")
        return TestConnectionResponse(ok=False, message="Internal server error during connection test")


def _row_to_response(row: asyncpg.Record, key_plain: str | None) -> BrokerConnectionResponse:
    key_preview = f"••••{key_plain[-4:]}" if key_plain and len(key_plain) >= 4 else "••••[INVALID]"
    ts_str = row.get("token_expires_at")
    if isinstance(ts_str, datetime):
        ts_str = ts_str.isoformat()
    return BrokerConnectionResponse(
        id=str(row["id"]),
        broker=row["broker"],
        base_url=row["base_url"],
        is_paper=row["is_paper"],
        is_active=row["is_active"],
        key_preview=key_preview,
        oauth_connected=bool(row.get("access_token")),
        token_status=_token_status(row),
        token_expires_at=ts_str,
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


# ── Standard API-key endpoints ─────────────────────────────────────────────────

@router.post("", response_model=BrokerConnectionResponse, status_code=status.HTTP_201_CREATED)
async def connect_broker(
    body: BrokerConnectRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> BrokerConnectionResponse:
    if body.broker == "alpaca":
        base_url = body.base_url or (_ALPACA_PAPER_URL if body.is_paper else _ALPACA_LIVE_URL)
        test = await _test_alpaca(body.api_key, body.api_secret, base_url)
        if not test.ok:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=test.message)
    else:
        base_url = body.base_url or ""
        if base_url:
            _validate_url(base_url, body.broker)

    repo = BrokerRepo(pool, current_user.tenant_id)
    row = await repo.upsert(
        broker=body.broker,
        key_encrypted=encrypt_key(body.api_key),
        secret_encrypted=encrypt_key(body.api_secret),
        base_url=base_url,
        is_paper=body.is_paper,
    )
    return _row_to_response(row, body.api_key)


@router.get("", response_model=list[BrokerConnectionResponse])
async def list_brokers(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[BrokerConnectionResponse]:
    repo = BrokerRepo(pool, current_user.tenant_id)
    rows = await repo.get_all()
    results = []
    for row in rows:
        key_plain: str | None = None
        if row.get("key_encrypted"):
            try:
                key_plain = decrypt_key(row["key_encrypted"])
            except ValueError:
                logger.error("Broker key decryption failed for connection %s", row["id"])
        results.append(_row_to_response(row, key_plain))
    return results


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker(
    connection_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    repo = BrokerRepo(pool, current_user.tenant_id)
    row = await repo.get_by_id(connection_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker connection not found")
    await repo.delete(connection_id)


@router.patch("/{connection_id}/test", response_model=TestConnectionResponse)
async def test_broker(
    connection_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TestConnectionResponse:
    repo = BrokerRepo(pool, current_user.tenant_id)
    row = await repo.get_by_id(connection_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker connection not found")

    try:
        key_plain    = decrypt_key(row["key_encrypted"])
        secret_plain = decrypt_key(row["secret_encrypted"])
    except ValueError:
        return TestConnectionResponse(ok=False, message="Key decryption failed — re-enter credentials")

    if row["broker"] == "alpaca":
        return await _test_alpaca(key_plain, secret_plain, row["base_url"] or _ALPACA_PAPER_URL)

    return TestConnectionResponse(ok=False, message=f"Live-test not implemented for {row['broker']}")


# ── OAuth login-URL endpoint ───────────────────────────────────────────────────

@router.get("/oauth/{broker}/login-url", response_model=OAuthLoginUrlResponse)
async def get_oauth_login_url(
    broker: str,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> OAuthLoginUrlResponse:
    """
    Returns the broker login URL (and a CSRF state token where applicable).
    The frontend redirects the user to this URL; the broker redirects back to
    /settings/brokers/oauth/callback with `code` / `request_token` in the query.
    """
    broker = broker.lower()
    repo = BrokerRepo(pool, current_user.tenant_id)

    if broker == "upstox":
        settings = get_settings()
        client_id = getattr(settings, "upstox_client_id", "")
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Upstox OAuth not configured — set UPSTOX_CLIENT_ID in .env",
            )
        state = secrets.token_urlsafe(24)
        await repo.set_oauth_state("upstox", state)
        return OAuthLoginUrlResponse(
            login_url=oauth.upstox_login_url(client_id, _oauth_redirect_uri("upstox"), state),
            state=state,
        )

    if broker == "zerodha":
        # For Zerodha, the api_key is per-user; it must already be stored.
        row = await repo.get_by_broker("zerodha")
        if not row or not row.get("key_encrypted"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Connect Zerodha with your API key & secret first, then click Login.",
            )
        api_key = decrypt_key(row["key_encrypted"])
        return OAuthLoginUrlResponse(
            login_url=oauth.zerodha_login_url(api_key),
            state=None,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"OAuth redirect not supported for broker '{broker}'. Use /oauth/{broker}/login for credential login.",
    )


# ── OAuth callback (code exchange) ────────────────────────────────────────────

@router.post("/oauth/callback", response_model=BrokerConnectionResponse)
async def oauth_callback(
    body: OAuthCallbackRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> BrokerConnectionResponse:
    """
    Exchange an OAuth authorization code (or Zerodha request_token) for tokens
    and persist them.  Called by the frontend after the broker redirects back.
    """
    repo = BrokerRepo(pool, current_user.tenant_id)
    settings = get_settings()

    if body.broker == "upstox":
        if not body.code:
            raise HTTPException(status_code=400, detail="Missing 'code' for Upstox OAuth callback")
        client_id     = getattr(settings, "upstox_client_id", "")
        client_secret = getattr(settings, "upstox_client_secret", "")
        if not client_id:
            raise HTTPException(status_code=503, detail="Upstox OAuth not configured")
        try:
            token_data = await oauth.upstox_exchange_code(
                client_id, client_secret, body.code, _oauth_redirect_uri("upstox"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        expires_at = oauth.token_expires_at(token_data["expires_in"])
        row = await repo.upsert_oauth(
            broker="upstox",
            key_encrypted=encrypt_key(client_id),
            secret_encrypted=encrypt_key(client_secret),
            access_token=encrypt_key(token_data["access_token"]),
            refresh_token=encrypt_key(token_data["refresh_token"]) if token_data["refresh_token"] else None,
            token_expires_at=expires_at,
            is_paper=False,
        )
        return _row_to_response(row, client_id)

    if body.broker == "zerodha":
        token = body.request_token or body.code
        if not token:
            raise HTTPException(status_code=400, detail="Missing 'request_token' for Zerodha OAuth callback")
        existing = await repo.get_by_broker("zerodha")
        if not existing:
            raise HTTPException(status_code=422, detail="Zerodha API key not found — connect first")
        api_key    = decrypt_key(existing["key_encrypted"])
        api_secret = decrypt_key(existing["secret_encrypted"])
        try:
            token_data = await oauth.zerodha_exchange_code(api_key, api_secret, token)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        expires_at = oauth.token_expires_at(token_data["expires_in"])
        await repo.update_oauth_tokens(
            broker="zerodha",
            access_token=encrypt_key(token_data["access_token"]),
            refresh_token=None,
            token_expires_at=expires_at,
        )
        row = await repo.get_by_broker("zerodha")
        return _row_to_response(row, api_key)

    raise HTTPException(status_code=400, detail=f"Unknown broker for OAuth callback: {body.broker!r}")


# ── AngelOne credential login (no redirect) ───────────────────────────────────

@router.post("/oauth/angelone/login", response_model=BrokerConnectionResponse)
async def angelone_login(
    body: AngelOneLoginRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> BrokerConnectionResponse:
    """
    Credential-based AngelOne login: clientcode + MPIN + TOTP.
    On success, stores the JWT access token (valid ~1 day).
    """
    try:
        token_data = await oauth.angelone_login(body.client_id, body.password, body.totp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    repo = BrokerRepo(pool, current_user.tenant_id)
    expires_at = oauth.token_expires_at(token_data["expires_in"])
    row = await repo.upsert_oauth(
        broker="angelone",
        key_encrypted=encrypt_key(body.client_id),
        secret_encrypted=encrypt_key(body.password),
        access_token=encrypt_key(token_data["access_token"]),
        refresh_token=encrypt_key(token_data["refresh_token"]) if token_data["refresh_token"] else None,
        token_expires_at=expires_at,
        is_paper=False,
        base_url="https://apiconnect.angelbroking.com",
    )
    return _row_to_response(row, body.client_id)
