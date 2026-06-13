'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, Check, CheckCheck, TrendingUp, AlertTriangle, Newspaper, Info } from 'lucide-react'
import { api, getAccessToken, portfolioSocketUrl } from '@/lib/api'
import { openReconnectingSocket } from '@/lib/ws'
import { cn } from '@/lib/utils'
import type { AppNotification, NotificationType, PortfolioWsMessage } from '@/lib/types'

const ICON: Record<NotificationType, typeof Bell> = {
  trade_executed: TrendingUp,
  bot_error: AlertTriangle,
  pnl_threshold: TrendingUp,
  news: Newspaper,
  system: Info,
}

const ICON_COLOR: Record<NotificationType, string> = {
  trade_executed: 'text-emerald-500',
  bot_error: 'text-rose-500',
  pnl_threshold: 'text-violet-500',
  news: 'text-blue-500',
  system: 'text-zinc-400',
}

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function NotificationPanel() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<AppNotification[]>([])
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const unread = items.filter((n) => !n.is_read).length

  const load = useCallback(() => {
    if (!getAccessToken()) return
    setLoading(true)
    api.listNotifications({ limit: 30 })
      .then((fetched) => {
        // Merge, don't replace: a live WS notification can arrive while this
        // request is in flight. Blindly setting `fetched` would drop it (the
        // server may not have included a row committed after the query ran).
        // Keep any current item whose id isn't in the fetched set, newest first.
        setItems((prev) => {
          const fetchedIds = new Set(fetched.map((n) => n.id))
          const liveOnly = prev.filter((n) => !fetchedIds.has(n.id))
          return [...liveOnly, ...fetched].slice(0, 50)
        })
      })
      .catch(() => { /* ignore */ })
      .finally(() => setLoading(false))
  }, [])

  // Initial load + live updates over the portfolio WS channel
  useEffect(() => {
    if (!getAccessToken()) return
    load()
    const sock = openReconnectingSocket<PortfolioWsMessage>(portfolioSocketUrl, {
      onMessage: (msg) => {
        if (msg.type === 'notification') {
          setItems((prev) => [msg.notification, ...prev].slice(0, 50))
        }
      },
    })
    return () => sock.close()
  }, [load])

  // Close on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const markRead = async (id: string) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    try { await api.markNotificationRead(id) } catch { /* ignore */ }
  }

  const markAll = async () => {
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
    try { await api.markAllNotificationsRead() } catch { /* ignore */ }
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        onClick={() => { setOpen((o) => !o); if (!open) load() }}
        title="Notifications"
        className="relative flex items-center justify-center w-[34px] h-[34px] rounded-xl
          text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800
          hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
      >
        <Bell className="w-[17px] h-[17px]" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full
            bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center
            shadow-[0_0_8px_rgba(244,63,94,0.6)]">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-[360px] max-h-[460px] z-50 rounded-2xl overflow-hidden
          bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 shadow-2xl flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-100 dark:border-white/[0.06]">
            <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Notifications</p>
            {unread > 0 && (
              <button onClick={markAll}
                className="inline-flex items-center gap-1 text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline">
                <CheckCheck className="w-3.5 h-3.5" /> Mark all read
              </button>
            )}
          </div>

          <div className="overflow-y-auto flex-1">
            {loading && items.length === 0 ? (
              <div className="py-12 flex justify-center">
                <span className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <div className="py-12 text-center text-sm text-zinc-400 dark:text-zinc-500">
                <Bell className="w-7 h-7 mx-auto mb-2 opacity-40" />
                No notifications yet.
              </div>
            ) : (
              items.map((n) => {
                const Icon = ICON[n.type] ?? Info
                return (
                  <div key={n.id}
                    className={cn(
                      'flex items-start gap-3 px-4 py-3 border-b border-zinc-50 dark:border-white/[0.04]',
                      'hover:bg-zinc-50 dark:hover:bg-white/[0.03] transition-colors',
                      !n.is_read && 'bg-violet-50/40 dark:bg-violet-500/[0.06]',
                    )}>
                    <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', ICON_COLOR[n.type] ?? 'text-zinc-400')} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate">{n.title}</p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 line-clamp-2">{n.body}</p>
                      <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-1">{timeAgo(n.created_at)}</p>
                    </div>
                    {!n.is_read && (
                      <button onClick={() => markRead(n.id)} title="Mark read"
                        className="flex-shrink-0 text-zinc-400 hover:text-violet-600 dark:hover:text-violet-400 transition-colors">
                        <Check className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
