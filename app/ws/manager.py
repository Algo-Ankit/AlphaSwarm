"""
WebSocket connection manager + Redis pub/sub bridge.

Channel naming:
  bars:{SYMBOL}:{EXCHANGE}:{TIMEFRAME}   live bar ticks
  portfolio:{tenant_id}                  P&L updates + notifications
  run:{run_id}                           strategy run status
"""
import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[channel].add(ws)
        logger.debug("WS connected channel=%s total=%d", channel, len(self._connections[channel]))

    async def disconnect(self, ws: WebSocket, channel: str) -> None:
        async with self._lock:
            self._connections[channel].discard(ws)
            if not self._connections[channel]:
                del self._connections[channel]

    async def broadcast(self, channel: str, message: dict) -> None:
        """Push a message to all clients on a channel. Removes dead connections."""
        dead: set[WebSocket] = set()
        for ws in list(self._connections.get(channel, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect(ws, channel)

    async def publish(self, redis_client, channel: str, message: dict) -> None:
        """Publish a message to a Redis channel (for cross-process broadcast)."""
        await redis_client.publish(channel, json.dumps(message))

    async def redis_listener(self, redis_client, channel_pattern: str) -> None:
        """
        Subscribe to a Redis pub/sub channel pattern and forward messages
        to all connected WebSocket clients on the matching channel.
        Call this as a background task on startup.
        """
        pubsub = redis_client.pubsub()
        await pubsub.psubscribe(channel_pattern)
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                try:
                    data = json.loads(message["data"])
                    await self.broadcast(channel, data)
                except Exception:
                    pass
        finally:
            await pubsub.punsubscribe(channel_pattern)


ws_manager = WebSocketManager()
