'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import type { StrategyRunListItem, RunOrderDetail } from '@/lib/types'
import { fmtDate, fmtCurrency, cn } from '@/lib/utils'
import {
  Activity, Play, CheckCircle2, XCircle, Clock,
  ChevronDown, ChevronUp, RefreshCw, ExternalLink,
  ShieldCheck, ShieldAlert, AlertTriangle, ArrowUpDown
} from 'lucide-react'

export default function RunsPage() {
  const [runs, setRuns] = useState<StrategyRunListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [modeFilter, setModeFilter] = useState<string>('all')
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [ordersMap, setOrdersMap] = useState<Record<string, RunOrderDetail[]>>({})
  const [ordersLoading, setOrdersLoading] = useState<string | null>(null)

  async function loadRuns() {
    setLoading(true)
    try {
      const data = await api.listRuns()
      setRuns(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRuns()
    const timer = setInterval(() => {
      api.listRuns().then(setRuns).catch(() => {})
    }, 10_000)
    return () => clearInterval(timer)
  }, [])

  async function handleToggleExpand(runId: string) {
    if (expandedRunId === runId) {
      setExpandedRunId(null)
      return
    }
    setExpandedRunId(runId)
    if (!ordersMap[runId]) {
      setOrdersLoading(runId)
      try {
        const orders = await api.listRunOrders(runId)
        setOrdersMap((prev) => ({ ...prev, [runId]: orders }))
      } catch {
        // ignore
      } finally {
        setOrdersLoading(null)
      }
    }
  }

  const filteredRuns = runs.filter((r) => {
    if (statusFilter !== 'all' && r.status !== statusFilter) return false
    if (modeFilter === 'paper' && !r.dry_run) return false
    if (modeFilter === 'live' && r.dry_run) return false
    return true
  })

  const runningCount = runs.filter((r) => r.status === 'running').length
  const completedCount = runs.filter((r) => r.status === 'completed').length
  const liveCount = runs.filter((r) => !r.dry_run).length

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto animate-slide-up relative z-10 pb-20">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight flex items-center gap-3">
              <Activity className="w-7 h-7 text-violet-500" />
              Strategy Execution Runs
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Audit logs, live agent task dispatches, and broker fill records across your swarm
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={loadRuns} disabled={loading}>
            <RefreshCw className={cn('w-3.5 h-3.5 mr-1.5', loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {/* Stats tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          <div className="px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Total Runs</span>
            <p className="text-2xl font-extrabold text-zinc-900 dark:text-zinc-100 mt-1">{runs.length}</p>
          </div>
          <div className="px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Active / Running</span>
            <p className="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-2">
              {runningCount}
              {runningCount > 0 && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
            </p>
          </div>
          <div className="px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Completed</span>
            <p className="text-2xl font-extrabold text-zinc-900 dark:text-zinc-100 mt-1">{completedCount}</p>
          </div>
          <div className="px-5 py-4 rounded-2xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Live Broker Runs</span>
            <p className="text-2xl font-extrabold text-violet-600 dark:text-violet-400 mt-1">{liveCount}</p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 p-2 rounded-xl bg-zinc-100/80 dark:bg-zinc-900/50 border border-zinc-200/60 dark:border-zinc-800/60">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-400 px-2">Status:</span>
            {(['all', 'running', 'completed', 'failed', 'queued'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all',
                  statusFilter === s
                    ? 'bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                )}
              >
                {s}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-400 px-2">Mode:</span>
            {(['all', 'paper', 'live'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setModeFilter(m)}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all',
                  modeFilter === m
                    ? 'bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Runs List */}
        {loading && runs.length === 0 ? (
          <div className="flex items-center justify-center py-24 text-zinc-400 text-sm">Loading runs…</div>
        ) : filteredRuns.length === 0 ? (
          <GlassCard padding="lg" className="text-center py-16">
            <Clock className="w-10 h-10 text-zinc-400 mx-auto mb-3 opacity-60" />
            <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">No strategy runs found</h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">
              Execute a strategy manually from the strategy detail page or enable the automated scheduler to see live run logs here.
            </p>
            <div className="mt-5">
              <Link href="/strategies">
                <Button size="sm">Browse Strategies</Button>
              </Link>
            </div>
          </GlassCard>
        ) : (
          <div className="space-y-3">
            {filteredRuns.map((r) => {
              const isExpanded = expandedRunId === r.id
              const orders = ordersMap[r.id] ?? []
              const isLoadingOrders = ordersLoading === r.id

              return (
                <GlassCard key={r.id} padding="none" className="overflow-hidden transition-all">
                  <div
                    onClick={() => handleToggleExpand(r.id)}
                    className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 px-6 py-4 cursor-pointer hover:bg-zinc-50/50 dark:hover:bg-zinc-800/40 transition-colors"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div
                        className={cn(
                          'w-2.5 h-2.5 rounded-full flex-shrink-0',
                          r.status === 'running'
                            ? 'bg-emerald-500 animate-pulse'
                            : r.status === 'completed'
                            ? 'bg-zinc-400 dark:bg-zinc-600'
                            : r.status === 'failed'
                            ? 'bg-rose-500'
                            : 'bg-amber-400'
                        )}
                      />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <Link
                            href={`/strategies/${r.strategy_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sm font-bold text-zinc-900 dark:text-zinc-100 hover:text-violet-500 transition-colors flex items-center gap-1"
                          >
                            {r.strategy_name}
                            <ExternalLink className="w-3 h-3 text-zinc-400" />
                          </Link>
                          <Badge
                            variant={
                              r.status === 'running'
                                ? 'success'
                                : r.status === 'failed'
                                ? 'danger'
                                : r.status === 'completed'
                                ? 'default'
                                : 'warning'
                            }
                          >
                            {r.status}
                          </Badge>
                          <span
                            className={cn(
                              'text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider',
                              r.dry_run
                                ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'
                                : 'bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300'
                            )}
                          >
                            {r.dry_run ? 'Paper' : 'Live'}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-zinc-400 mt-1">
                          <span className="font-mono text-[11px] truncate">{r.id.slice(0, 8)}…</span>
                          <span>·</span>
                          <span>{r.exchange}</span>
                          <span>·</span>
                          <span>{r.symbols.join(', ')}</span>
                          <span>·</span>
                          <span>{fmtDate(r.created_at)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 self-end sm:self-center flex-shrink-0">
                      <div className="text-right">
                        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                          {r.orders_count} {r.orders_count === 1 ? 'order' : 'orders'}
                        </span>
                        {r.error && (
                          <p className="text-[11px] text-rose-500 max-w-[200px] truncate">{r.error}</p>
                        )}
                      </div>
                      <div className="p-1 rounded-lg text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200">
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Order Audit Drawer */}
                  {isExpanded && (
                    <div className="border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-900/60 p-6 animate-slide-up">
                      <h4 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-emerald-500" />
                        Order Intent & Risk Audit ({orders.length})
                      </h4>

                      {isLoadingOrders ? (
                        <p className="text-xs text-zinc-400 py-4">Loading order details…</p>
                      ) : orders.length === 0 ? (
                        <p className="text-xs text-zinc-400 py-3">
                          No orders placed in this run {r.error ? `(Failed: ${r.error})` : '(No signals generated)'}.
                        </p>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr className="border-b border-zinc-200 dark:border-zinc-800 text-zinc-400 text-[10px] uppercase tracking-wider">
                                <th className="pb-2">Symbol</th>
                                <th className="pb-2">Side</th>
                                <th className="pb-2">Qty</th>
                                <th className="pb-2">Est. Price</th>
                                <th className="pb-2">Fill Price</th>
                                <th className="pb-2">Notional</th>
                                <th className="pb-2">Risk Gate</th>
                                <th className="pb-2">Status</th>
                                <th className="pb-2">Time</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-200/50 dark:divide-zinc-800/50">
                              {orders.map((o) => (
                                <tr key={o.id} className="font-mono text-[11px]">
                                  <td className="py-2.5 font-bold text-zinc-900 dark:text-zinc-100">{o.symbol}</td>
                                  <td className="py-2.5">
                                    <span
                                      className={cn(
                                        'px-1.5 py-0.5 rounded uppercase text-[10px] font-bold',
                                        o.side.toLowerCase() === 'buy'
                                          ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400'
                                          : 'bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400'
                                      )}
                                    >
                                      {o.side}
                                    </span>
                                  </td>
                                  <td className="py-2.5 text-zinc-700 dark:text-zinc-300">{o.quantity}</td>
                                  <td className="py-2.5 text-zinc-500">${o.estimated_price.toFixed(2)}</td>
                                  <td className="py-2.5 text-zinc-900 dark:text-zinc-100 font-semibold">
                                    {o.fill_price ? `$${o.fill_price.toFixed(2)}` : '—'}
                                  </td>
                                  <td className="py-2.5 text-zinc-700 dark:text-zinc-300">
                                    ${o.estimated_notional.toLocaleString()}
                                  </td>
                                  <td className="py-2.5">
                                    <span
                                      className={cn(
                                        'text-[10px] font-semibold',
                                        o.risk_status === 'approved' ? 'text-emerald-500' : 'text-rose-500'
                                      )}
                                    >
                                      {o.risk_status}
                                    </span>
                                  </td>
                                  <td className="py-2.5 capitalize text-zinc-500">{o.broker_status ?? 'simulated'}</td>
                                  <td className="py-2.5 text-zinc-400">{fmtDate(o.created_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </GlassCard>
              )
            })}
          </div>
        )}
      </div>
    </AppShell>
  )
}
