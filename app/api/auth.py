import logging

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.repositories.brokers import BrokerRepo
from app.db.repositories.users import AuthUserRepo, RefreshTokenRepo, TenantRepo
from app.services import oauth_manager as oauth
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    create_state_token,
    equalize_login_timing,
    get_grace_period_expiry,
    get_refresh_token_expiry,
    hash_password,
    verify_password,
    verify_state_token,
)
from app.services.broker_crypto import encrypt_key
from app.services.email import send_welcome_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    tenant_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    email: str
    role: str
    display_name: str
    tenant_name: str
    plan: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    user_repo = AuthUserRepo(pool)
    tenant_repo = TenantRepo(pool)
    token_repo = RefreshTokenRepo(pool)

    if await user_repo.get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    tenant = await tenant_repo.create(name=body.tenant_name, plan="founding_member")
    user = await user_repo.create(
        tenant_id=tenant["id"],
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="owner",
    )

    access_token = create_access_token(
        user_id=str(user["id"]),
        tenant_id=str(tenant["id"]),
        email=body.email,
        role="owner",
    )
    raw_refresh = create_refresh_token()
    await token_repo.create(user["id"], raw_refresh, get_refresh_token_expiry())

    # Best-effort welcome/verification email (no-op if SendGrid unconfigured).
    await send_welcome_email(body.email, user["display_name"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user["id"]),
        tenant_id=str(tenant["id"]),
        email=body.email,
        role="owner",
        display_name=user["display_name"],
        tenant_name=tenant["name"],
        plan=tenant["plan"],
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    user_repo = AuthUserRepo(pool)
    tenant_repo = TenantRepo(pool)
    token_repo = RefreshTokenRepo(pool)

    user = await user_repo.get_by_email(body.email)
    if not user:
        # Constant-time-ish response: burn a bcrypt verify so a missing email
        # is indistinguishable (by latency) from a wrong password.
        equalize_login_timing(body.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if user["password_hash"] is None:
        # Broker-identity account (e.g. created via "Continue with Upstox") —
        # there is no password to verify against.
        equalize_login_timing(body.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account signs in with a broker. Use 'Continue with Upstox'.",
        )
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    tenant = await tenant_repo.get_by_id(user["tenant_id"])

    access_token = create_access_token(
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
        email=body.email,
        role=user["role"],
    )
    raw_refresh = create_refresh_token()
    await token_repo.create(user["id"], raw_refresh, get_refresh_token_expiry())

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
        email=body.email,
        role=user["role"],
        display_name=user["display_name"],
        tenant_name=tenant["name"],
        plan=tenant["plan"],
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("60/minute")
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    token_repo = RefreshTokenRepo(pool)

    record = await token_repo.get_by_raw_token(body.refresh_token)
    if not record:
        # Reuse detection: a token that WAS rotated but is past its grace window
        # being presented again is the classic refresh-token-theft signature
        # (attacker and victim both hold the old token; whoever comes second
        # trips this). Revoke the entire session family for that user.
        stolen_user_id = await token_repo.find_reused_token_user(body.refresh_token)
        if stolen_user_id:
            await token_repo.delete_all_for_user(stolen_user_id)
            logger.warning(
                "Refresh token reuse detected for user %s — all sessions revoked",
                stolen_user_id,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )

    raw_refresh = create_refresh_token()

    # If this token was already rotated (rotated_to_hash is set) we are inside the
    # 45-second grace window — a second concurrent tab sent the same token that Tab A
    # already rotated. Issue a brand-new R3 token with a full TTL so this tab does
    # not end up holding the expiring R1 token (which dies when the grace period ends).
    if record["rotated_to_hash"]:
        raw_refresh_for_tab = create_refresh_token()
        await token_repo.create(record["user_id"], raw_refresh_for_tab, get_refresh_token_expiry())
        access_token = create_access_token(
            user_id=str(record["user_id"]),
            tenant_id=str(record["tenant_id"]),
            email=record["email"],
            role=record["role"],
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_for_tab,  # full-TTL token, not the expiring R1
            user_id=str(record["user_id"]),
            tenant_id=str(record["tenant_id"]),
            email=record["email"],
            role=record["role"],
            display_name=record["display_name"],
            tenant_name=record["tenant_name"],
            plan=record["plan"],
        )

    # Normal rotation path: mark old token with grace period, issue new token
    await token_repo.rotate(
        old_raw_token=body.refresh_token,
        new_raw_token=raw_refresh,
        grace_period_until=get_grace_period_expiry(),
    )
    await token_repo.create(record["user_id"], raw_refresh, get_refresh_token_expiry())

    access_token = create_access_token(
        user_id=str(record["user_id"]),
        tenant_id=str(record["tenant_id"]),
        email=record["email"],
        role=record["role"],
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(record["user_id"]),
        tenant_id=str(record["tenant_id"]),
        email=record["email"],
        role=record["role"],
        display_name=record["display_name"],
        tenant_name=record["tenant_name"],
        plan=record["plan"],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    await RefreshTokenRepo(pool).delete_by_raw_token(body.refresh_token)


# ── Broker-identity login ("Continue with Upstox") ────────────────────────────
# One click does BOTH things a new Indian user needs: creates/authenticates the
# AlphaSwarm account (the broker's KYC-verified email is the identity) AND
# stores the broker OAuth tokens, so the brokerage is connected for live
# execution before they ever see the dashboard. No API key copy-pasting.


class BrokerLoginUrlResponse(BaseModel):
    login_url: str
    state: str


class UpstoxLoginCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=1024)


def _upstox_login_redirect_uri() -> str:
    # Distinct from the broker-CONNECT callback (/settings/brokers/oauth/callback):
    # this one lands on the pre-auth login flow. Both URIs must be registered on
    # the platform's Upstox app.
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/login/upstox/callback"


@router.get("/broker/upstox/login-url", response_model=BrokerLoginUrlResponse)
@limiter.limit("20/minute")
async def upstox_login_url(request: Request) -> BrokerLoginUrlResponse:
    settings = get_settings()
    if not settings.upstox_client_id or not settings.upstox_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upstox sign-in is not configured on this server.",
        )
    # Pre-auth flow: no tenant row exists to hold the state, so it is a signed
    # short-lived token verified at callback time (stateless CSRF).
    state = create_state_token("upstox-login")
    return BrokerLoginUrlResponse(
        login_url=oauth.upstox_login_url(
            settings.upstox_client_id, _upstox_login_redirect_uri(), state
        ),
        state=state,
    )


@router.post("/broker/upstox/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def upstox_login_callback(
    request: Request,
    body: UpstoxLoginCallbackRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    settings = get_settings()
    if not settings.upstox_client_id or not settings.upstox_client_secret:
        raise HTTPException(status_code=503, detail="Upstox sign-in is not configured.")

    if not verify_state_token(body.state, "upstox-login"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="OAuth state invalid or expired — restart the Upstox sign-in.",
        )

    try:
        token_data = await oauth.upstox_exchange_code(
            settings.upstox_client_id,
            settings.upstox_client_secret,
            body.code,
            _upstox_login_redirect_uri(),
        )
        profile = await oauth.upstox_get_profile(token_data["access_token"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not profile["email"]:
        raise HTTPException(
            status_code=422,
            detail="Upstox did not return an email for this account — sign in with email instead.",
        )

    user_repo = AuthUserRepo(pool)
    tenant_repo = TenantRepo(pool)
    token_repo = RefreshTokenRepo(pool)

    user = await user_repo.get_by_email(profile["email"])
    if user:
        tenant = await tenant_repo.get_by_id(user["tenant_id"])
    else:
        tenant = await tenant_repo.create(
            name=f"{profile['user_name']}'s Workspace", plan="founding_member"
        )
        user = await user_repo.create(
            tenant_id=tenant["id"],
            email=profile["email"],
            password_hash=None,
            display_name=profile["user_name"],
            role="owner",
            auth_provider="upstox",
        )
        await send_welcome_email(profile["email"], user["display_name"])

    # Persist the broker tokens so the brokerage is immediately usable for
    # execution — signing in IS connecting the broker.
    broker_repo = BrokerRepo(pool, user["tenant_id"])
    await broker_repo.upsert_oauth(
        broker="upstox",
        key_encrypted=encrypt_key(settings.upstox_client_id),
        secret_encrypted=encrypt_key(settings.upstox_client_secret),
        access_token=encrypt_key(token_data["access_token"]),
        refresh_token=encrypt_key(token_data["refresh_token"])
        if token_data["refresh_token"]
        else None,
        token_expires_at=oauth.token_expires_at(token_data["expires_in"]),
        is_paper=False,
    )

    access_token = create_access_token(
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
        email=profile["email"],
        role=user["role"],
    )
    raw_refresh = create_refresh_token()
    await token_repo.create(user["id"], raw_refresh, get_refresh_token_expiry())

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
        email=profile["email"],
        role=user["role"],
        display_name=user["display_name"],
        tenant_name=tenant["name"],
        plan=tenant["plan"],
    )
