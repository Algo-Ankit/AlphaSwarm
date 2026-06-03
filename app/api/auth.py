import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.users import AuthUserRepo, RefreshTokenRepo, TenantRepo
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    get_grace_period_expiry,
    get_refresh_token_expiry,
    hash_password,
    verify_password,
)

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


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user["id"]),
        tenant_id=str(tenant["id"]),
        email=body.email,
        role="owner",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    user_repo = AuthUserRepo(pool)
    token_repo = RefreshTokenRepo(pool)

    user = await user_repo.get_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

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
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> TokenResponse:
    token_repo = RefreshTokenRepo(pool)

    record = await token_repo.get_by_raw_token(body.refresh_token)
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

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
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    await RefreshTokenRepo(pool).delete_by_raw_token(body.refresh_token)
