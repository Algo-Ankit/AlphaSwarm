"""
WebSocket endpoints.
Auth: JWT passed as ?token= query param (validated on handshake, not per-message).
Client heartbeat: send any text message within 90s to stay alive.

Channels implemented:
  /v1/ws/bars/{symbol}   — latest cached bar, pushed every ~5s
  /v1/ws/portfolio       — P&L updates + notifications (receives Redis pushes)
  /v1/ws/run/{run_id}    — strategy run status updates
"""
import asyncio
import logging
import uuid as _uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.db.connection import get_pool
from app.services.auth import decode_access_token
from app.services.market_data import get_bars
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_HEARTBEAT_TIMEOUT = 90.0   # seconds before server closes idle connection
_BAR_PUSH_INTERVAL = 5.0    # seconds between cached-bar pushes


def _auth(token: str) -> dict | None:
    return decode_access_token(token)


@router.websocket("/v1/ws/bars/{symbol}")
async def ws_bars(
    websocket: WebSocket,
    symbol: str,
    timeframe: str = Query("1m"),
    exchange: str = Query("NASDAQ"),
    token: str = Query(""),
) -> None:
    payload = _auth(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    channel = f"bars:{symbol.upper()}:{exchange.upper()}:{timeframe}"
    await ws_manager.connect(websocket, channel)
    pool = get_pool()

    async def push_latest() -> None:
        """Push the latest cached bar on a fixed interval."""
        while True:
            try:
                bars = await get_bars(symbol, exchange, timeframe, limit=1, pool=pool)
                if bars:
                    await websocket.send_json({"type": "bar", **bars[-1].to_dict()})
            except Exception as exc:
                logger.warning("push_latest failed for %s %s — closing connection: %s", symbol, timeframe, exc)
                try:
                    await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                except Exception:
                    pass
                break
            await asyncio.sleep(_BAR_PUSH_INTERVAL)

    push_task = asyncio.create_task(push_latest())
    try:
        while True:
            # Receive client messages (pings). Times out if client goes silent.
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_HEARTBEAT_TIMEOUT
                )
                if msg == "ping":
                    try:
                        await websocket.send_json({"type": "pong"})
                    except Exception:
                        break
            except asyncio.TimeoutError:
                try:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        pass
    finally:
        push_task.cancel()
        try:
            await push_task
        except asyncio.CancelledError:
            pass
        await ws_manager.disconnect(websocket, channel)


@router.websocket("/v1/ws/portfolio")
async def ws_portfolio(
    websocket: WebSocket,
    token: str = Query(""),
) -> None:
    payload = _auth(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    tenant_id = payload.get("tenant_id", "")
    try:
        tenant_uuid = _uuid.UUID(tenant_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    channel = f"portfolio:{tenant_uuid}"
    await ws_manager.connect(websocket, channel)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_HEARTBEAT_TIMEOUT
                )
                if msg == "ping":
                    # The socket may have closed between receive and send; a raw
                    # send then raises ConnectionClosed and crashes the handler.
                    try:
                        await websocket.send_json({"type": "pong"})
                    except Exception:
                        break
            except asyncio.TimeoutError:
                try:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket, channel)


@router.websocket("/v1/ws/run/{run_id}")
async def ws_run(
    websocket: WebSocket,
    run_id: str,
    token: str = Query(""),
) -> None:
    payload = _auth(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify this run belongs to the authenticated user's tenant
    tenant_id = payload.get("tenant_id", "")
    try:
        run_uuid = _uuid.UUID(run_id)
        tenant_uuid = _uuid.UUID(tenant_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM strategy_runs WHERE id = $1 AND tenant_id = $2",
            run_uuid, tenant_uuid,
        )
    if not exists:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    channel = f"run:{run_id}"
    await ws_manager.connect(websocket, channel)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_HEARTBEAT_TIMEOUT
                )
                if msg == "ping":
                    try:
                        await websocket.send_json({"type": "pong"})
                    except Exception:
                        break
            except asyncio.TimeoutError:
                try:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket, channel)
