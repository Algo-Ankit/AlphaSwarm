'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AppShell }       from '@/components/layout/AppShell'
import { GlassCard }      from '@/components/ui/GlassCard'
import { Button }         from '@/components/ui/Button'
import { Badge }          from '@/components/ui/Badge'
import { ExecutionLog }   from '@/components/terminal/ExecutionLog'
import { api }            from '@/lib/api'
import type { Strategy, StrategyRunResponse } from '@/lib/types'
import { fmtDate, fmtCurrency, cn } from '@/lib/utils'
import {
  Play, Square, Activity, ArrowLeft, Clock,
  History, Database, ShieldAlert, CheckCircle2, Terminal,
} from 'lucide-react'

export default function StrategyDetailPage() {
  const params  = useParams()
  const router  = useRouter()
  const id      = params.id as string

  const [strategy,  setStrategy]  = useState<Strategy | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [running,   setRunning]   = useState(false)
  const [lastRun,   setLastRun]   = useState<StrategyRunResponse | null>(null)

  useEffect(() => {
    api.getStrategy(id)
      .then(setStrategy)
      .catch(() => router.push('/'))
      .finally(() => setLoading(false))
  }, [id, router])

  async function handleRun() {
    if (!strategy) return
    setRunning(true)
    try {
      const run = await api.runStrategy(strategy.id, true)
      setLastRun(run)
      // Running state clears when the WebSocket receives `completed` or `failed`.
      // We listen in ExecutionLog — set a safety timeout of 30s.
      setTimeout(() => setRunning(false), 30_000)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Run failed')
      setRunning(false)
    }
  }

  if (loading) return (
    <AppShell>
      <div className="animate-pulse space-y-6">
        <div className="h-10 w-48 glass-card opacity-50" />
        <div className="h-52 glass-card opacity-40" />
        <div className="h-96 glass-card opacity-30" />
      </div>
    </AppShell>
  )

  if (!strategy) return null

  const isQuant = (strategy as { creation_mode?: string }).creation_mode === 'quant'

  return (
    <AppShell>
      <div className="space-y-8 pb-20" style={{ animation: 'fadeIn 0.2s ease-out' }}>

        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-6">
          <div>
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase
                tracking-widest text-zinc-400 hover:text-violet-500 transition-colors mb-4"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Dashboard
            </Link>

            <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight">
              {strategy.name}
            </h1>

            <div className="flex items-center flex-wrap gap-2.5 mt-3">
              <Badge
                variant={strategy.status === 'active' ? 'success' : 'muted'}
                dot
                pulse={strategy.status === 'active'}
              >
                {strategy.status}
              </Badge>
              {isQuant && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md
                  bg-emerald-100 text-emerald-700
                  dark:bg-emerald-500/15 dark:text-emerald-300">
                  Python strategy
                </span>
              )}
              {strategy.symbols.map((s) => (
                <span key={s} className="px-2.5 py-0.5 text-xs font-bold rounded-lg
                  bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 font-mono">
                  {s}
                </span>
              ))}
              <span className="text-sm text-zinc-400 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />{strategy.timeframe}
              </span>
            </div>
          </div>

          <Button
            size="lg"
            variant={running ? 'secondary' : 'primary'}
            onClick={handleRun}
            disabled={running}
            className={cn(
              'flex-shrink-0',
              !running && 'shadow-[0_4px_20px_rgba(109,40,217,0.35)] hover:shadow-[0_6px_28px_rgba(109,40,217,0.5)]',
            )}
          >
            {running
              ? <><Activity className="w-4 h-4 mr-2 animate-spin" /> Running…</>
              : <><Play className="w-4 h-4 mr-2" /> Run Agent</>}
          </Button>
        </div>

        {/* ── Body: two columns ───────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Left column — code + terminal */}
          <div className="lg:col-span-2 space-y-6">

            {/* Generated logic */}
            <GlassCard padding="md">
              <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest
                text-zinc-500 dark:text-zinc-500 mb-4">
                <Database className="w-3.5 h-3.5 text-violet-500" />
                {isQuant ? 'Strategy Code' : 'Compiled Logic'}
              </h3>
              <div className={cn(
                'p-4 rounded-xl border font-mono text-[12px] leading-relaxed',
                'whitespace-pre-wrap overflow-x-auto',
                'bg-zinc-50 border-zinc-200 text-zinc-700',
                'dark:bg-zinc-900/70 dark:border-zinc-800 dark:text-zinc-300',
              )}>
                {strategy.generated_logic || '— logic not yet compiled —'}
              </div>
            </GlassCard>

            {/* Original prompt */}
            <GlassCard padding="md">
              <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest
                text-zinc-500 dark:text-zinc-500 mb-3">
                <History className="w-3.5 h-3.5 text-fuchsia-500" />
                {isQuant ? 'Submitted as' : 'Original Prompt'}
              </h3>
              <p className={cn(
                'text-sm leading-relaxed italic px-4 py-3 rounded-xl border',
                'text-zinc-600 dark:text-zinc-400',
                'bg-zinc-50 border-zinc-100 dark:bg-zinc-900/50 dark:border-zinc-800',
              )}>
                "{strategy.prompt}"
              </p>
            </GlassCard>

            {/* ── Execution Terminal ──────────────────────────────────── */}
            <div>
              <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest
                text-zinc-500 dark:text-zinc-500 mb-3">
                <Terminal className="w-3.5 h-3.5 text-emerald-500" />
                Execution Log
                {lastRun && (
                  <span className="ml-auto text-[10px] normal-case tracking-normal font-medium
                    text-zinc-400 dark:text-zinc-600">
                    run/{lastRun.run_id.slice(0, 8)}
                  </span>
                )}
              </h3>

              {lastRun ? (
                <ExecutionLog runId={lastRun.run_id} />
              ) : (
                /* Idle state — faux terminal */
                <div className="rounded-xl overflow-hidden border border-zinc-800">
                  <div className="flex items-center gap-1.5 px-4 py-2.5 bg-[#1a1a2e] border-b border-zinc-800">
                    <span className="w-3 h-3 rounded-full bg-rose-500/50" />
                    <span className="w-3 h-3 rounded-full bg-amber-500/50" />
                    <span className="w-3 h-3 rounded-full bg-emerald-500/50" />
                    <span className="font-mono text-[11px] text-zinc-600 ml-3">no active run</span>
                  </div>
                  <div className="bg-[#0d0d1a] h-40 p-4 flex items-center gap-2
                    font-mono text-[12px] text-zinc-600">
                    <span className="animate-pulse">▊</span>
                    <span>Press <span className="text-violet-400">Run Agent</span> to start a strategy execution…</span>
                  </div>
                </div>
              )}
            </div>

          </div>

          {/* Right column — risk settings */}
          <div className="space-y-5">
            <GlassCard padding="md">
              <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest
                text-zinc-500 dark:text-zinc-500 mb-5">
                <ShieldAlert className="w-3.5 h-3.5 text-rose-500" />
                Risk Settings
              </h3>
              <div className="space-y-0">
                {[
                  { label: 'Max Order',    value: fmtCurrency(strategy.risk.max_order_notional),   color: 'text-zinc-900 dark:text-zinc-100' },
                  { label: 'Daily Limit',  value: fmtCurrency(strategy.risk.max_daily_notional),   color: 'text-rose-600 dark:text-rose-400' },
                  { label: 'Created',      value: fmtDate(strategy.created_at ?? ''),               color: 'text-zinc-900 dark:text-zinc-100' },
                ].map(({ label, value, color }) => (
                  <div key={label}
                    className="flex items-center justify-between py-3
                      border-b border-zinc-100 dark:border-white/[0.05] last:border-0">
                    <span className="text-sm text-zinc-500 dark:text-zinc-400">{label}</span>
                    <span className={cn('text-sm font-bold', color)}>{value}</span>
                  </div>
                ))}

                <div className="flex items-center justify-between py-3">
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">Paper Trading</span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-zinc-100 dark:border-white/[0.05]">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400
                  dark:text-zinc-600 mb-2.5">
                  Allowed Symbols
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {strategy.risk.allowed_symbols.map((s) => (
                    <span key={s} className="px-2 py-0.5 text-[11px] font-bold font-mono rounded-md
                      bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </GlassCard>

            {/* Metadata */}
            <GlassCard padding="md">
              <h3 className="text-[11px] font-bold uppercase tracking-widest text-zinc-500
                dark:text-zinc-500 mb-3">
                Meta
              </h3>
              <div className="space-y-2 font-mono text-[11px]">
                <div className="flex justify-between">
                  <span className="text-zinc-500">id</span>
                  <span className="text-zinc-400 truncate max-w-[120px]">{strategy.id.slice(0, 12)}…</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">timeframe</span>
                  <span className="text-zinc-400">{strategy.timeframe}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">mode</span>
                  <span className={isQuant ? 'text-emerald-500' : 'text-violet-500'}>
                    {isQuant ? 'quant' : 'ai-generated'}
                  </span>
                </div>
              </div>
            </GlassCard>
          </div>

        </div>
      </div>
    </AppShell>
  )
}
