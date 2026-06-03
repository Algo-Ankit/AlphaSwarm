'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import type { Strategy, StrategyRunResponse, TaskStatusResponse } from '@/lib/types'
import { fmtDate, fmtCurrency, cn } from '@/lib/utils'
import { Play, Square, Activity, ArrowLeft, Clock, History, Database, CheckCircle2, ShieldAlert } from 'lucide-react'

export default function StrategyDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string
  const [strategy, setStrategy] = useState<Strategy | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState<StrategyRunResponse | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatusResponse | null>(null)

  useEffect(() => {
    api.getStrategy(id)
      .then(setStrategy)
      .catch(() => router.push('/'))
      .finally(() => setLoading(false))
  }, [id, router])

  function pollTask(taskId: string) {
    const i = setInterval(async () => {
      try {
        const t = await api.getTaskStatus(taskId)
        setTaskStatus(t)
        if (t.celery_status === 'SUCCESS' || t.celery_status === 'FAILURE') {
          clearInterval(i)
          setRunning(false)
        }
      } catch {
        clearInterval(i)
        setRunning(false)
      }
    }, 1500)
  }

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
      setRunning(false)
    }
  }

  // Task result fields come from the Celery worker payload, not the run response
  const taskResult = taskStatus?.result as Record<string, unknown> | null | undefined
  const simulatedPnl = typeof taskResult?.simulated_pnl === 'number' ? taskResult.simulated_pnl : null
  const brokerMode = typeof taskResult?.broker_mode === 'string' ? taskResult.broker_mode : null

  if (loading) return (
    <AppShell>
      <div className="animate-pulse space-y-6 max-w-4xl mx-auto">
        <div className="h-10 w-32 glass-card opacity-50" />
        <div className="h-48 w-full glass-card opacity-40 rounded-3xl" />
        <div className="h-64 w-full glass-card opacity-30 rounded-3xl" />
      </div>
    </AppShell>
  )

  if (!strategy) return null

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto animate-fade-in relative z-10 pb-20">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-zinc-400 hover:text-violet-500 transition-colors mb-4">
              <ArrowLeft className="w-4 h-4" />Back to Dashboard
            </Link>
            <h2 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-600 dark:from-white dark:to-zinc-400 tracking-tight">{strategy.name}</h2>
            <div className="flex items-center gap-3 mt-4">
              <Badge variant={strategy.status === 'active' ? 'success' : 'muted'} dot className="px-3 py-1 text-sm shadow-sm">
                {strategy.status === 'active' ? 'Active' : 'Inactive'}
              </Badge>
              <div className="flex gap-1.5">
                {strategy.symbols.map(s => (
                  <span key={s} className="px-2.5 py-1 text-xs font-bold rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 text-zinc-700 dark:text-zinc-300 shadow-sm border border-black/[0.03] dark:border-white/[0.05]">{s}</span>
                ))}
              </div>
              <span className="text-sm font-medium text-zinc-400 flex items-center gap-1.5">
                <Clock className="w-4 h-4" />{strategy.timeframe}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Button size="lg" variant={strategy.status === 'active' ? 'secondary' : 'primary'} onClick={handleRun} disabled={running} className="shadow-[0_0_15px_rgba(139,92,246,0.2)] hover:shadow-[0_0_25px_rgba(139,92,246,0.4)] transition-all h-12 px-6">
              {running ? <Activity className="w-5 h-5 mr-2 animate-spin" /> : strategy.status === 'active' ? <Square className="w-5 h-5 mr-2" /> : <Play className="w-5 h-5 mr-2" />}
              {running ? 'Executing…' : strategy.status === 'active' ? 'Stop Agent' : 'Start Agent'}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="col-span-1 lg:col-span-2 space-y-8">
            <GlassCard padding="lg" className="border-t-[3px] border-t-violet-500 hover:shadow-[0_8px_30px_rgba(139,92,246,0.12)]">
              <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-4 flex items-center gap-2"><Database className="w-4 h-4 text-violet-500" /> Compiled Logic</h3>
              <div className="bg-zinc-50/80 dark:bg-zinc-900/80 p-5 rounded-2xl border border-zinc-200 dark:border-zinc-800 font-mono text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap shadow-inner leading-relaxed">
                {strategy.generated_logic}
              </div>
            </GlassCard>

            <GlassCard padding="lg">
              <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-4 flex items-center gap-2"><History className="w-4 h-4 text-fuchsia-500" /> Original Prompt</h3>
              <p className="text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400 italic bg-zinc-50 dark:bg-zinc-900/50 p-5 rounded-2xl border border-black/[0.03] dark:border-white/[0.03]">"{strategy.prompt}"</p>
            </GlassCard>

            {lastRun && taskStatus && (
              <GlassCard padding="lg" className="animate-slide-up border border-indigo-500/20 bg-indigo-500/5">
                <div className="flex items-center justify-between mb-5">
                  <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2"><Activity className="w-5 h-5 text-indigo-500" /> Latest Execution</h3>
                  <Badge
                    variant={taskStatus.celery_status === 'SUCCESS' ? 'success' : taskStatus.celery_status === 'FAILURE' ? 'danger' : 'info'}
                    className="shadow-sm"
                  >
                    {taskStatus.celery_status}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-5">
                  <div className="bg-white/50 dark:bg-zinc-900/50 p-4 rounded-2xl border border-black/[0.03] dark:border-white/[0.03]">
                    <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-1">Simulated PnL</p>
                    <p className={cn(
                      "text-xl font-extrabold",
                      simulatedPnl !== null && simulatedPnl > 0 ? "text-emerald-500"
                        : simulatedPnl !== null && simulatedPnl < 0 ? "text-rose-500"
                        : "text-zinc-900 dark:text-zinc-100"
                    )}>
                      {simulatedPnl !== null ? fmtCurrency(simulatedPnl) : '—'}
                    </p>
                  </div>
                  <div className="bg-white/50 dark:bg-zinc-900/50 p-4 rounded-2xl border border-black/[0.03] dark:border-white/[0.03]">
                    <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mb-1">Broker Mode</p>
                    <p className="text-[15px] font-bold text-zinc-900 dark:text-zinc-100 capitalize">{brokerMode ?? '—'}</p>
                  </div>
                </div>
              </GlassCard>
            )}

            {taskStatus && taskStatus.celery_status !== 'SUCCESS' && taskStatus.celery_status !== 'FAILURE' && (
              <GlassCard padding="lg" className="animate-pulse bg-violet-500/5 border-violet-500/20">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-violet-500/20 flex items-center justify-center">
                    <Activity className="w-4 h-4 text-violet-500 animate-spin" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Executing strategy on Celery worker...</h4>
                    <p className="text-xs font-medium text-zinc-500 mt-0.5">Task ID: {taskStatus.task_id.slice(0, 8)}</p>
                  </div>
                </div>
              </GlassCard>
            )}
          </div>

          <div className="col-span-1 space-y-6">
            <GlassCard padding="lg">
              <h3 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-5 flex items-center gap-2"><ShieldAlert className="w-4 h-4 text-rose-500" /> Risk Settings</h3>
              <div className="space-y-4">
                <div className="flex justify-between items-center py-3 border-b border-black/[0.05] dark:border-white/[0.05]">
                  <span className="text-sm font-medium text-zinc-500">Max Order</span>
                  <span className="text-[15px] font-extrabold text-zinc-900 dark:text-zinc-100">{fmtCurrency(strategy.risk.max_order_notional)}</span>
                </div>
                <div className="flex justify-between items-center py-3 border-b border-black/[0.05] dark:border-white/[0.05]">
                  <span className="text-sm font-medium text-zinc-500">Daily Loss Limit</span>
                  <span className="text-[15px] font-extrabold text-rose-500">{fmtCurrency(strategy.risk.max_daily_notional)}</span>
                </div>
                <div className="flex justify-between items-center py-3 border-b border-black/[0.05] dark:border-white/[0.05]">
                  <span className="text-sm font-medium text-zinc-500">Paper Trading</span>
                  <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                </div>
                <div className="pt-2">
                  <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 block mb-3">Allowed Symbols</span>
                  <div className="flex flex-wrap gap-2">
                    {strategy.risk.allowed_symbols.map(s => (
                      <span key={s} className="px-2.5 py-1 text-xs font-bold rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">{s}</span>
                    ))}
                  </div>
                </div>
              </div>
            </GlassCard>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
