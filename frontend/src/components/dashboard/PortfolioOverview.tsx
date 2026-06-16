'use client'
import { useEffect, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import { Wallet, TrendingUp, TrendingDown, Activity, Wifi, PieChart } from 'lucide-react'
import { GlassCard } from '@/components/ui/GlassCard'
import { EquityCurve } from '@/components/charts/EquityCurve'
import { DonutChart } from '@/components/charts/DonutChart'
import { api, getAccessToken, portfolioSocketUrl } from '@/lib/api'
import { openReconnectingSocket, type WsStatus } from '@/lib/ws'
import { cn } from '@/lib/utils'
import type { AllocationSlice, PortfolioSnapshot, PortfolioSummary, PortfolioWsMessage } from '@/lib/types'

// ── XIRR (Newton-Raphson) ──────────────────────────────────────────────────────
function xirr(cashFlows: { amount: number; date: Date }[]): number | null {
  if (cashFlows.length < 2) return null
  const t0 = cashFlows[0].date.getTime()
  const years = cashFlows.map((cf) => (cf.date.getTime() - t0) / (365.25 * 86_400_000))

  const npv = (r: number) =>
    cashFlows.reduce((sum, cf, i) => sum + cf.amount / Math.pow(1 + r, years[i]), 0)
  const dnpv = (r: number) =>
    cashFlows.reduce((sum, cf, i) => sum - (years[i] * cf.amount) / Math.pow(1 + r, years[i] + 1), 0)

  let r = 0.1
  for (let i = 0; i < 100; i++) {
    const f  = npv(r)
    const df = dnpv(r)
    if (Math.abs(df) < 1e-12) break
    const rNew = r - f / df
    if (Math.abs(rNew - r) < 1e-8) return isFinite(rNew) ? rNew : null
    r = rNew
  }
  return isFinite(r) ? r : null
}

function computeXirr(snapshots: PortfolioSnapshot[]): number | null {
  if (snapshots.length < 2) return null
  const first = snapshots[0]
  const last  = snapshots[snapshots.length - 1]
  const equity0 = first.total_equity
  const equityN = last.total_equity
  if (equity0 <= 0) return null
  const flows = [
    { amount: -equity0, date: new Date(first.snapshot_time) },
    { amount: equityN,  date: new Date(last.snapshot_time) },
  ]
  return xirr(flows)
}

function fmtUsd(n: number): string {
  const sign = n < 0 ? '-' : ''
  return sign + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(r: number): string {
  return (r >= 0 ? '+' : '') + (r * 100).toFixed(1) + '%'
}

export function PortfolioOverview() {
  const { resolvedTheme } = useTheme()
  const dark = resolvedTheme === 'dark'

  const [summary,   setSummary]   = useState<PortfolioSummary | null>(null)
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [alloc,     setAlloc]     = useState<AllocationSlice[]>([])
  const [loading,   setLoading]   = useState(true)
  const [wsStatus,  setWsStatus]  = useState<WsStatus>('closed')
  const [showAlloc, setShowAlloc] = useState(false)
  const liveArrived = useRef(false)

  useEffect(() => {
    if (!getAccessToken()) return
    Promise.all([
      api.getPortfolioSummary().catch(() => null),
      api.getPortfolioSnapshots(200).catch(() => [] as PortfolioSnapshot[]),
      api.getPortfolioAllocation().catch(() => [] as AllocationSlice[]),
    ]).then(([s, snaps, al]) => {
      if (liveArrived.current) return
      setSummary(s)
      setSnapshots(snaps)
      setAlloc(al)
    }).finally(() => setLoading(false))

    const sock = openReconnectingSocket<PortfolioWsMessage>(portfolioSocketUrl, {
      onStatus: setWsStatus,
      onMessage: (msg) => {
        if (msg.type !== 'portfolio') return
        liveArrived.current = true
        const snap: PortfolioSnapshot = {
          snapshot_time:      msg.snapshot_time,
          total_equity:       msg.total_equity,
          open_pnl:           msg.open_pnl,
          realized_pnl_today: msg.realized_pnl_today,
          active_strategies:  msg.active_strategies,
        }
        setSnapshots((prev) => [...prev, snap].slice(-300))
        setSummary({ ...snap, has_data: true })
      },
    })
    return () => sock.close()
  }, [])

  if (loading) return <div className="glass-card h-64 animate-pulse" style={{ opacity: 0.5 }} />

  const openPnl  = summary?.open_pnl ?? 0
  const realized = summary?.realized_pnl_today ?? 0
  const xirrRate = computeXirr(snapshots)

  type Tone = 'up' | 'down' | 'neutral'
  const toneCls: Record<Tone, string> = {
    up:      'text-emerald-600 dark:text-emerald-400',
    down:    'text-rose-600 dark:text-rose-400',
    neutral: 'text-zinc-900 dark:text-zinc-100',
  }

  const cards: { label: string; value: string | number; icon: typeof Wallet; tone: Tone }[] = [
    {
      label: 'Total Equity',
      value: fmtUsd(summary?.total_equity ?? 0),
      icon: Wallet,
      tone: 'neutral',
    },
    {
      label: xirrRate != null ? `XIRR ${fmtPct(xirrRate)}` : 'XIRR',
      value: xirrRate != null ? fmtPct(xirrRate) : '—',
      icon: xirrRate != null && xirrRate >= 0 ? TrendingUp : TrendingDown,
      tone: xirrRate == null ? 'neutral' : xirrRate >= 0 ? 'up' : 'down',
    },
    {
      label: "Today's Realized",
      value: fmtUsd(realized),
      icon: realized >= 0 ? TrendingUp : TrendingDown,
      tone: realized >= 0 ? 'up' : 'down',
    },
    { label: 'Active Strategies', value: summary?.active_strategies ?? 0, icon: Activity, tone: 'neutral' },
  ]

  return (
    <GlassCard padding="lg">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Portfolio</h2>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAlloc((v) => !v)}
            className={cn(
              'inline-flex items-center gap-1.5 text-xs font-medium transition-colors',
              showAlloc
                ? 'text-violet-600 dark:text-violet-400'
                : 'text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300',
            )}
          >
            <PieChart className="w-3.5 h-3.5" />
            Allocation
          </button>
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-zinc-400 dark:text-zinc-500">
            <Wifi className={cn('w-3.5 h-3.5', wsStatus === 'open' ? 'text-emerald-500' : 'text-zinc-400')} />
            {wsStatus === 'open' ? 'Live' : 'Reconnecting'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map((c) => (
          <div key={c.label} className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 bg-zinc-100 dark:bg-white/[0.05]">
              <c.icon className={cn('w-4 h-4', toneCls[c.tone])} />
            </div>
            <div className="min-w-0">
              <p className={cn('text-lg font-bold leading-none tabular-nums truncate', toneCls[c.tone])}>
                {c.value}
              </p>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-500 mt-1 font-medium truncate">
                {c.label}
              </p>
            </div>
          </div>
        ))}
      </div>

      {showAlloc && alloc.length > 0 ? (
        <div className="border-t border-zinc-100 dark:border-white/[0.05] pt-5">
          <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-4">
            Asset Allocation
          </p>
          <DonutChart slices={alloc} size={140} thickness={24} className="mx-auto max-w-[200px]" />
        </div>
      ) : (
        <EquityCurve snapshots={snapshots} dark={dark} />
      )}

      {!summary?.has_data && (
        <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-3">
          P&L is a display aggregate from your positions — the platform never holds funds.
        </p>
      )}
      {xirrRate != null && (
        <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-1.5">
          XIRR is annualised return computed from equity snapshots. Not financial advice.
        </p>
      )}
    </GlassCard>
  )
}
