'use client'
import { useEffect, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import { Wallet, TrendingUp, TrendingDown, Activity, Wifi } from 'lucide-react'
import { GlassCard } from '@/components/ui/GlassCard'
import { EquityCurve } from '@/components/charts/EquityCurve'
import { api, getAccessToken, portfolioSocketUrl } from '@/lib/api'
import { openReconnectingSocket, type WsStatus } from '@/lib/ws'
import { cn } from '@/lib/utils'
import type { PortfolioSnapshot, PortfolioSummary, PortfolioWsMessage } from '@/lib/types'

function fmtUsd(n: number): string {
  const sign = n < 0 ? '-' : ''
  return sign + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function PortfolioOverview() {
  const { resolvedTheme } = useTheme()
  const dark = resolvedTheme === 'dark'

  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [wsStatus, setWsStatus] = useState<WsStatus>('closed')
  // True once a live WS snapshot has arrived. The initial HTTP fetch resolves
  // asynchronously; if a WS message landed first, its newer data must NOT be
  // overwritten by the slower (and now-stale) HTTP response.
  const liveArrived = useRef(false)

  useEffect(() => {
    if (!getAccessToken()) return
    Promise.all([
      api.getPortfolioSummary().catch(() => null),
      api.getPortfolioSnapshots(200).catch(() => []),
    ]).then(([s, snaps]) => {
      if (liveArrived.current) return  // live data already supersedes the fetch
      setSummary(s)
      setSnapshots(snaps)
    }).finally(() => setLoading(false))

    const sock = openReconnectingSocket<PortfolioWsMessage>(portfolioSocketUrl, {
      onStatus: setWsStatus,
      onMessage: (msg) => {
        if (msg.type !== 'portfolio') return
        liveArrived.current = true
        const snap: PortfolioSnapshot = {
          snapshot_time: msg.snapshot_time,
          total_equity: msg.total_equity,
          open_pnl: msg.open_pnl,
          realized_pnl_today: msg.realized_pnl_today,
          active_strategies: msg.active_strategies,
        }
        setSnapshots((prev) => [...prev, snap].slice(-300))
        setSummary({ ...snap, has_data: true })
      },
    })
    return () => sock.close()
  }, [])

  if (loading) {
    return <div className="glass-card h-64 animate-pulse" style={{ opacity: 0.5 }} />
  }

  const openPnl = summary?.open_pnl ?? 0
  const realized = summary?.realized_pnl_today ?? 0

  type Tone = 'up' | 'down' | 'neutral'
  const cards: { label: string; value: string | number; icon: typeof Wallet; tone: Tone }[] = [
    { label: 'Total Equity', value: fmtUsd(summary?.total_equity ?? 0), icon: Wallet, tone: 'neutral' },
    { label: 'Open P&L', value: fmtUsd(openPnl), icon: openPnl >= 0 ? TrendingUp : TrendingDown, tone: openPnl >= 0 ? 'up' : 'down' },
    { label: "Today's Realized", value: fmtUsd(realized), icon: realized >= 0 ? TrendingUp : TrendingDown, tone: realized >= 0 ? 'up' : 'down' },
    { label: 'Active Strategies', value: summary?.active_strategies ?? 0, icon: Activity, tone: 'neutral' },
  ]

  const toneCls: Record<Tone, string> = {
    up: 'text-emerald-600 dark:text-emerald-400',
    down: 'text-rose-600 dark:text-rose-400',
    neutral: 'text-zinc-900 dark:text-zinc-100',
  }

  return (
    <GlassCard padding="lg">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Portfolio</h2>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-zinc-400 dark:text-zinc-500">
          <Wifi className={cn('w-3.5 h-3.5', wsStatus === 'open' ? 'text-emerald-500' : 'text-zinc-400')} />
          {wsStatus === 'open' ? 'Live' : 'Reconnecting'}
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map((c) => (
          <div key={c.label} className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 bg-zinc-100 dark:bg-white/[0.05]">
              <c.icon className={cn('w-4 h-4', toneCls[c.tone])} />
            </div>
            <div className="min-w-0">
              <p className={cn('text-lg font-bold leading-none tabular-nums truncate', toneCls[c.tone])}>{c.value}</p>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-500 mt-1 font-medium">{c.label}</p>
            </div>
          </div>
        ))}
      </div>

      <EquityCurve snapshots={snapshots} dark={dark} />
      {!summary?.has_data && (
        <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-3">
          P&L is a display aggregate from your positions — the platform never holds funds.
        </p>
      )}
    </GlassCard>
  )
}
