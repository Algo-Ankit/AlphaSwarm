/**
 * Reconnecting WebSocket helper.
 *
 * Roadmap rule (ARCHITECTURE.md, "Starting Phase 6?"): WS connections must
 * reconnect automatically on disconnect with exponential backoff, capped at 30s.
 *
 * The server (app/api/ws.py) closes idle sockets after 90s of silence, so we
 * send a heartbeat ping well within that window; any text frame resets the timer.
 */

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000
const HEARTBEAT_MS = 30_000

export type WsStatus = 'connecting' | 'open' | 'closed'

export interface ReconnectingSocketHandlers<T> {
  onMessage: (data: T) => void
  onStatus?: (status: WsStatus) => void
}

export interface ReconnectingSocket {
  close: () => void
}

/**
 * Opens a self-healing WebSocket to `url`. Returns a handle whose `close()`
 * permanently tears it down (no further reconnects). `url` is resolved lazily
 * on each (re)connect so a refreshed JWT in the query string is picked up.
 */
export function openReconnectingSocket<T = unknown>(
  url: string | (() => string),
  { onMessage, onStatus }: ReconnectingSocketHandlers<T>,
): ReconnectingSocket {
  let ws: WebSocket | null = null
  let attempt = 0
  let stopped = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  const resolveUrl = () => (typeof url === 'function' ? url() : url)

  const clearTimers = () => {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  }

  const scheduleReconnect = () => {
    if (stopped) return
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS)
    attempt += 1
    reconnectTimer = setTimeout(connect, delay)
  }

  function connect() {
    if (stopped) return
    onStatus?.('connecting')
    try {
      ws = new WebSocket(resolveUrl())
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      attempt = 0
      onStatus?.('open')
      heartbeatTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
      }, HEARTBEAT_MS)
    }

    ws.onmessage = (ev) => {
      let parsed: T
      try {
        parsed = JSON.parse(ev.data as string) as T
      } catch {
        return // ignore non-JSON frames (e.g. pong text)
      }
      onMessage(parsed)
    }

    ws.onclose = () => {
      if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
      onStatus?.('closed')
      scheduleReconnect()
    }

    ws.onerror = () => {
      ws?.close() // triggers onclose → reconnect
    }
  }

  connect()

  return {
    close() {
      stopped = true
      clearTimers()
      if (ws) {
        ws.onclose = null // prevent reconnect on intentional close
        ws.close()
        ws = null
      }
    },
  }
}
