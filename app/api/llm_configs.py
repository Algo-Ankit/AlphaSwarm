"""
LLM Configs API — POST/GET/DELETE /v1/llm-configs
Users bring their own LLM API keys for NL strategy generation.
Keys are encrypted at rest with the same Fernet key used for broker keys.
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.llm_configs import LLMConfigRepo
from app.services.broker_crypto import decrypt_key, encrypt_key

router = APIRouter(prefix="/v1/llm-configs", tags=["llm-configs"])

_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq":      "https://api.groq.com/openai/v1",
    "openai":    "https://api.openai.com/v1",
    "together":  "https://api.together.xyz/v1",
    "anthropic": "https://api.anthropic.com/v1",
}


class LLMConfigCreate(BaseModel):
    label:    str  = Field(min_length=1, max_length=80)
    provider: str  = Field(default="custom", pattern="^(groq|openai|together|anthropic|custom)$")
    base_url: str  = Field(min_length=5, max_length=512)
    api_key:  str  = Field(min_length=1, max_length=512)
    model:    str  = Field(min_length=1, max_length=120)


class LLMConfigResponse(BaseModel):
    id:          str
    label:       str
    provider:    str
    base_url:    str
    model:       str
    key_preview: str
    created_at:  str


def _row_to_response(row: asyncpg.Record) -> LLMConfigResponse:
    try:
        plain = decrypt_key(row["key_encrypted"])
        preview = f"••••{plain[-4:]}" if len(plain) >= 4 else "••••"
    except ValueError:
        preview = "••••[invalid]"
    return LLMConfigResponse(
        id=str(row["id"]),
        label=row["label"],
        provider=row["provider"],
        base_url=row["base_url"],
        model=row["model"],
        key_preview=preview,
        created_at=row["created_at"].isoformat(),
    )


@router.post("", response_model=LLMConfigResponse, status_code=status.HTTP_201_CREATED)
async def add_llm_config(
    body: LLMConfigCreate,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> LLMConfigResponse:
    # For known providers, silently fix base_url if user left it as the placeholder
    if body.provider in _PROVIDER_BASE_URLS and not body.base_url.startswith("http"):
        base_url = _PROVIDER_BASE_URLS[body.provider]
    else:
        base_url = body.base_url

    repo = LLMConfigRepo(pool, current_user.tenant_id)
    row = await repo.create(
        owner_user_id=current_user.user_id,
        label=body.label,
        provider=body.provider,
        base_url=base_url,
        key_encrypted=encrypt_key(body.api_key),
        model=body.model,
    )
    return _row_to_response(row)


@router.get("", response_model=list[LLMConfigResponse])
async def list_llm_configs(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[LLMConfigResponse]:
    repo = LLMConfigRepo(pool, current_user.tenant_id)
    rows = await repo.get_all()
    return [_row_to_response(r) for r in rows]


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    config_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    repo = LLMConfigRepo(pool, current_user.tenant_id)
    row = await repo.get_by_id(config_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM config not found")
    await repo.delete(config_id)
