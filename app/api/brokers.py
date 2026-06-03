from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.brokers import BrokerRepo
from app.services.broker_crypto import decrypt_key, encrypt_key

router = APIRouter(prefix="/v1/brokers", tags=["brokers"])

_ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
_ALPACA_LIVE_URL = "https://api.alpaca.markets"


class BrokerConnectRequest(BaseModel):
    broker: str = Field(default="alpaca", pattern="^(alpaca|upstox|zerodha)$")
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
    created_at: str
    updated_at: str


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    account_id: str | None = None


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
            return TestConnectionResponse(ok=True, message="Connected successfully", account_id=acct_id)
        if resp.status_code in (401, 403):
            return TestConnectionResponse(ok=False, message="Invalid API key or secret")
        return TestConnectionResponse(ok=False, message=f"Alpaca returned HTTP {resp.status_code}")
    except httpx.TimeoutException:
        return TestConnectionResponse(ok=False, message="Connection timed out — check the base URL")
    except Exception as exc:
        return TestConnectionResponse(ok=False, message=f"Connection error: {str(exc)[:120]}")


def _row_to_response(row: asyncpg.Record, key_plain: str) -> BrokerConnectionResponse:
    return BrokerConnectionResponse(
        id=str(row["id"]),
        broker=row["broker"],
        base_url=row["base_url"],
        is_paper=row["is_paper"],
        is_active=row["is_active"],
        key_preview=f"••••{key_plain[-4:]}",
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


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
        try:
            key_plain = decrypt_key(row["key_encrypted"])
        except ValueError:
            key_plain = "????"
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
        key_plain = decrypt_key(row["key_encrypted"])
        secret_plain = decrypt_key(row["secret_encrypted"])
    except ValueError:
        return TestConnectionResponse(ok=False, message="Key decryption failed — re-enter credentials")

    if row["broker"] == "alpaca":
        return await _test_alpaca(key_plain, secret_plain, row["base_url"] or _ALPACA_PAPER_URL)

    return TestConnectionResponse(ok=False, message=f"Test not implemented for {row['broker']}")
