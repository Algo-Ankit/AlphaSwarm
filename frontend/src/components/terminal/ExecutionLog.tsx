'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Circle } from 'lucide-react'

/* ── Types ───────────────────────────────────────────────────────────────── */
type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SIGNAL' | 'RISK' | 'ORDER' | 'STATUS'
type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'rejected'

interface LogEntry {
  id: string
  ts: string
  level: LogLevel
  msg: string
}

/* ── Styling maps ─────────────────────────────────────────────────────────── */
const LEVEL_STYLE: Record<LogLevel, { badge: string; text: string; label: string }> = {
  INFO:   { badge: 'bg-zinc-800 text-zinc-400',           text: 'text-zinc-300',   label: 'INFO  ' },
  WARN:   { badge: 'bg-amber-900/50 text-amber-400',      text: 'text-amber-300',  label: 'WARN  ' },
  ERROR:  { badge: 'bg-rose-900/50 text-rose-400',        text: 'text-rose-300',   label: 'ERROR ' },
  SIGNAL: { badge: 'bg-sky-900/50 text-sky-400',          text: 'text-sky-300',    label: 'SIGNAL' },
  RISK:   { badge: 'bg-orange-900/50 text-orange-400',    text: 'text-orange-300', label: 'RISK  ' },
  ORDER:  { badge: 'bg-emerald-900/50 text-emerald-400',  text: 'text-emerald-300',label: 'ORDER ' },
  STATUS: { badge: 'bg-violet-900/50 text-violet-400',    text: 'text-violet-300', label: 'STATUS' },
}

const STATUS_COLOR: Record<RunStatus, string> = {
  queued:    'bg-amber-500',
  running:   'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]',
  completed: 'bg-zinc-500',
  failed:    'bg-rose-500',
  rejected:  'bg-orange-500',
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function fmtTime(ts: string): string {
  try {
    const d = new Date(ts)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${hh}:${mm}:${ss}.${ms}`
  } catch { return ts }
}

let _id = 0
function nextId() { return String(++_id) }

/* ── Component ───────────────────────────────────────────────────────────── */
interface ExecutionLogProps {
  runId: string
  className?: string
}

export function ExecutionLog({ runId, className }: ExecutionLogProps) {
  const [entries, setEntries]       = useState<LogEntry[]>([])
  const [connected, setConnected]   = useState(false)
  const [runStatus, setRunStatus]   = useState<RunStatus | null>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  const scrollRef  = useRef<HTMLDivElement>(null)
  const wsRef      = useRef<WebSocket | null>(null)

  /* ── Add entry ───────────────────────────────────────────────────────── */
  const push = useCallback((level: LogLevel, msg: string, ts?: string) => {
    setEntries(prev => [
      ...prev.slice(-800),          // cap at 800 lines
      { id: nextId(), ts: ts ?? new Date().toISOString(), level, msg },
    ])
  }, [])

  /* ── WebSocket connection ────────────────────────────────────────────── */
  useEffect(() => {
    const token = getAccessToken()
    if (!token || !runId) return

    const base = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')
    const url  = `${base}/v1/ws/run/${runId}?token=${token}`
    const ws   = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      push('STATUS', `Connected — run ${runId.slice(0, 8)}…`)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string)

        if (msg.type === 'run_log') {
          const level = (msg.level ?? 'INFO') as LogLevel
          push(level, msg.msg as string, msg.ts as string)

        } else if (msg.type === 'run_status') {
          const status = msg.status as RunStatus
          setRunStatus(status)
          push('STATUS', `→ ${status.toUpperCase()}${msg.msg ? `  ${msg.msg}` : ''}`, msg.ts as string)

        } else if (msg.type === 'bar') {
          push('INFO', `Bar  ${msg.symbol}  close=${msg.c}  vol=${msg.v}`, msg.t as string)
        }
        // ignore pong
      } catch { /* malformed frame */ }
    }

    ws.onclose = (ev) => {
      setConnected(false)
      push('STATUS', `Disconnected (code ${ev.code})`)
    }

    ws.onerror = () => push('ERROR', 'WebSocket error — check API server')

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30_000)

    return () => {
      clearInterval(ping)
      ws.close()
    }
  }, [runId, push])

  /* ── Auto-scroll ─────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!autoScroll) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries, autoScroll])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    setAutoScroll(nearBottom)
  }

  /* ── Render ──────────────────────────────────────────────────────────── */
  return (
    <div className={cn('rounded-xl overflow-hidden border border-zinc-800 shadow-xl', className)}>

      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#1a1a2e] border-b border-zinc-800 select-none">
        {/* macOS traffic lights */}
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-rose-500/80" />
          <span className="w-3 h-3 rounded-full bg-amber-500/80" />
          <span className="w-3 h-3 rounded-full bg-emerald-500/80" />
          <span className="font-mono text-[11px] text-zinc-500 ml-3 tracking-tight">
            run/{runId.slice(0, 8)}
          </span>
        </div>

        {/* Status + connection indicator */}
        <div className="flex items-center gap-3">
          {runStatus && (
            <div className="flex items-center gap-1.5">
              <span className={cn('w-2 h-2 rounded-full flex-shrink-0', STATUS_COLOR[runStatus])} />
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                {runStatus}
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <Circle
              className={cn('w-2 h-2 fill-current flex-shrink-0',
                connected ? 'text-emerald-500' : 'text-zinc-600'
              )}
            />
            <span className="text-[10px] text-zinc-500 font-mono">
              {connected ? 'live' : 'offline'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Log body ─────────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-80 overflow-y-auto bg-[#0d0d1a] p-4 space-y-[3px]"
        style={{ scrollbarWidth: 'thin', scrollbarColor: '#27272a transparent' }}
      >
        {/* Prompt line */}
        <div className="flex items-center gap-2 mb-3 pb-3 border-b border-zinc-800">
          <span className="text-violet-500 font-mono text-[12px]">alphaswarm</span>
          <span className="text-zinc-600 font-mono text-[12px]">$</span>
          <span className="text-zinc-400 font-mono text-[12px]">
            run --id {runId.slice(0, 8)} --watch
          </span>
        </div>

        {entries.length === 0 ? (
          <div className="flex items-center gap-2 text-zinc-600 font-mono text-[12px]">
            <span className="animate-pulse">▊</span>
            <span>Waiting for execution…</span>
          </div>
        ) : (
          entries.map((e) => {
            const s = LEVEL_STYLE[e.level] ?? LEVEL_STYLE.INFO
            return (
              <div key={e.id} className="flex items-start gap-3 font-mono text-[12px] leading-relaxed group">
                {/* Timestamp */}
                <span className="text-zinc-600 flex-shrink-0 tabular-nums text-[11px] mt-px">
                  {fmtTime(e.ts)}
                </span>
                {/* Level badge */}
                <span className={cn(
                  'flex-shrink-0 text-[9px] font-bold px-1.5 py-[2px] rounded',
                  'tracking-wider uppercase mt-px',
                  s.badge,
                )}>
                  {e.level}
                </span>
                {/* Message */}
                <span className={cn('break-all', s.text)}>
                  {e.msg}
                </span>
              </div>
            )
          })
        )}

        {/* Blinking cursor at end */}
        {connected && (
          <div className="flex items-center gap-2 font-mono text-[12px] text-zinc-600 mt-2">
            <span className="animate-pulse">▊</span>
          </div>
        )}
      </div>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-[#1a1a2e] border-t border-zinc-800">
        <span className="font-mono text-[10px] text-zinc-600">
          {entries.length} lines
        </span>
        {!autoScroll && (
          <button
            onClick={() => {
              setAutoScroll(true)
              const el = scrollRef.current
              if (el) el.scrollTop = el.scrollHeight
            }}
            className="font-mono text-[10px] text-violet-500 hover:text-violet-400 transition-colors"
          >
            ↓ scroll to bottom
          </button>
        )}
        <span className="font-mono text-[10px] text-zinc-700">
          AlphaSwarm execution log
        </span>
      </div>
    </div>
  )
}
