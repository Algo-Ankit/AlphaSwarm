'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { STATUS_BADGE, RUN_BADGE } from '@/lib/constants'
import { fmtDate, fmtCurrency } from '@/lib/utils'
import type { Strategy, StrategyRunResponse, TaskStatusResponse } from '@/lib/types'
import { ArrowLeft, Play, Clock, Shield, Code2, RefreshCw } from 'lucide-react'

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [strategy, setStrategy] = useState<Strategy | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState<StrategyRunResponse | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatusResponse | null>(null)
  const [polling, setPolling] = useState(false)

  useEffect(() => {
    api.getStrategy(id)
      .then(setStrategy)
      .catch(() => router.push('/'))
      .finally(() => setLoading(false))
  }, [id, router])

  const pollTask = useCallback((taskId: string) => {
    setPolling(true)
    const t = setInterval(async () => {
      try {
        const s = await api.getTaskStatus(taskId)
        setTaskStatus(s)
        if (['SUCCESS', 'FAILURE', 'REVOKED'].includes(s.celery_status)) {
          clearInterval(t)
          setPolling(false)
        }
      } catch { clearInterval(t); setPolling(false) }
    }, 1500)
  }, [])

  async function handleRun() {
    if (!strategy) return
    setRunning(true)
    setTaskStatus(null)
    try {
      const run = await api.runStrategy(strategy.id, true)
      setLastRun(run)
      pollTask(run.task_id)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Run failed')
    } finally { setRunning(false) }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="space-y-4 animate-pulse max-w-4xl">
          <div className="h-8 w-56 rounded-xl bg-zinc-100 dark:bg-zinc-800" />
          <div className="grid grid-cols-3 gap-4">
            {[1,2,3].map((i) => <div key={i} className="h-36 glass-card opacity-50" />)}
          </div>
        </div>
      </AppShell>
    )
  }

  if (!strategy) return null

  const statusVariant = STATUS_BADGE[strategy.status] ?? 'default'
  const celeryStatus = taskStatus?.celery_status?.toLowerCase() ?? ''
  const runVariant = RUN_BADGE[celeryStatus as keyof typeof RUN_BADGE] ?? RUN_BADGE[lastRun?.status as keyof typeof RUN_BADGE] ?? 'default'

  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <Link href="/" className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors mb-3">
              <ArrowLeft className="w-3.5 h-3.5" />Back to Dashboard
            </Link>
            <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight truncate">{strategy.name}</h2>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <Badge variant={statusVariant} dot pulse={strategy.status === 'active'}>{strategy.status}</Badge>
              {strategy.symbols.map((sym) => (
                <span key={sym} className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-md bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {sym}
                </span>
              ))}
              <span className="flex items-center gap-1 text-xs text-zinc-400">
                <Clock className="w-3.5 h-3.5" />{strategy.timeframe}
              </span>
            </div>
          </div>
          <Button onClick={handleRun} loading={running || polling} size="lg" className="flex-shrink-0">
            <Play className="w-4 h-4" />Run Strategy
          </Button>
        </div>

        {/* Info + Risk */}
        <div className="grid grid-cols-3 gap-4">
          <GlassCard padding="md" className="col-span-2">
            <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-3">Strategy Description</h3>
            <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">{strategy.prompt}</p>
          </GlassCard>

          <GlassCard padding="md">
            <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5" />Risk Config
            </h3>
            <div className="space-y-3">
              <div>
                <p className="text-[11px] text-zinc-400">Max Order</p>
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-0.5">{fmtCurrency(strategy.risk.max_order_notional)}</p>
              </div>
              <div>
                <p className="text-[11px] text-zinc-400">Daily Cap</p>
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mt-0.5">{fmtCurrency(strategy.risk.max_daily_notional)}</p>
              </div>
              <div>
                <p className="text-[11px] text-zinc-400 mb-1">Mode</p>
                <Badge variant="success" dot>{strategy.risk.paper_trading_only ? 'Paper' : 'Live'}</Badge>
              </div>
            </div>
          </GlassCard>
        </div>

        {/* Compiled logic */}
        {strategy.generated_logic && (
          <GlassCard padding="md">
            <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Code2 className="w-3.5 h-3.5" />Compiled Logic
            </h3>
            <pre className="text-xs font-mono text-zinc-600 dark:text-zinc-300 bg-zinc-50 dark:bg-black/30 rounded-xl p-4 overflow-auto whitespace-pre-wrap leading-relaxed">
              {strategy.generated_logic}
            </pre>
          </GlassCard>
        )}

        {/* Run result */}
        {lastRun && (
          <GlassCard padding="md" glow>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">Last Run</h3>
              {polling && (
                <span className="flex items-center gap-1.5 text-[11px] text-zinc-400">
                  <RefreshCw className="w-3 h-3 animate-spin" />Polling…
                </span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <p className="text-[11px] text-zinc-400">Run ID</p>
                <p className="text-xs font-mono text-zinc-700 dark:text-zinc-300 mt-0.5 truncate">{lastRun.run_id.slice(0, 12)}…</p>
              </div>
              <div>
                <p className="text-[11px] text-zinc-400 mb-1">Status</p>
                <Badge variant={runVariant} dot pulse={polling}>
                  {taskStatus?.celery_status ?? lastRun.status}
                </Badge>
              </div>
              <div>
                <p className="text-[11px] text-zinc-400 mb-1">Mode</p>
                <Badge variant="info">{lastRun.dry_run ? 'Dry Run' : 'Live'}</Badge>
              </div>
            </div>
            {taskStatus?.result && (
              <div className="border-t border-black/[0.05] dark:border-white/[0.05] pt-4">
                <p className="text-[11px] text-zinc-400 mb-2">Result</p>
                <pre className="text-xs font-mono text-zinc-600 dark:text-zinc-300 bg-zinc-50 dark:bg-black/30 rounded-xl p-4 overflow-auto leading-relaxed">
                  {JSON.stringify(taskStatus.result, null, 2)}
                </pre>
              </div>
            )}
          </GlassCard>
        )}
      </div>
    </AppShell>
  )
}
