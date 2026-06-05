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
import type { Strategy, StrategyRunResponse, BacktestResult } from '@/lib/types'
import { fmtDate, fmtCurrency, cn } from '@/lib/utils'
import { normalizeTimeframe } from '@/lib/constants'
import {
  Play, Activity, ArrowLeft, Clock,
  History, Database, ShieldAlert, CheckCircle2, Terminal,
  FlaskConical, TrendingUp, TrendingDown, BarChart3, Zap,
} from 'lucide-react'

// ── Equity curve SVG sparkline ────────────────────────────────────────────────
function EquityCurve({ data, initial }: { data: number[]; initial: number }) {
  if (data.length < 2) return null
  const W = 600, H = 120
  const min = Math.min(...data) * 0.998
  const max = Math.max(...data) * 1.002
  const range = max - min || 1

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((v - min) / range) * (H - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const isGain = data[data.length - 1] >= initial
  const stroke = isGain ? '#10b981' : '#ef4444'
  const fill   = isGain ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)'
  const lastX  = ((data.length - 1) / (data.length - 1)) * W

  const polyline = pts.join(' ')
  const area = `${pts[0]} ${polyline} ${lastX},${H} 0,${H}`

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height: 100 }}
    >
      {/* baseline */}
      <line
        x1="0" y1={H - ((initial - min) / range) * (H - 4) - 2}
        x2={W} y2={H - ((initial - min) / range) * (H - 4) - 2}
        stroke="rgba(255,255,255,0.08)" strokeWidth="1" strokeDasharray="4,4"
      />
      {/* fill area */}
      <polygon points={area} fill={fill} />
      {/* line */}
      <polyline points={polyline} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricTile({
  label, value, sub, up,
}: { label: string; value: string; sub?: string; up?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 px-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-100 dark:border-zinc-800">
      <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{label}</span>
      <span className={cn(
        'text-xl font-extrabold tabular-nums',
        up === true  && 'text-emerald-600 dark:text-emerald-400',
        up === false && 'text-rose-600 dark:text-rose-400',
        up === undefined && 'text-zinc-900 dark:text-zinc-100',
      )}>
        {value}
      </span>
      {sub && <span className="text-[11px] text-zinc-400">{sub}</span>}
    </div>
  )
}

export default function StrategyDetailPage() {
  const params  = useParams()
  const router  = useRouter()
  const id      = params.id as string

  const [strategy,  setStrategy]  = useState<Strategy | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [running,   setRunning]   = useState(false)
  const [lastRun,   setLastRun]   = useState<StrategyRunResponse | null>(null)

  // backtest state
  const [btSymbol,    setBtSymbol]    = useState('')
  const [btTimeframe, setBtTimeframe] = useState('1d')
  const [btLimit,     setBtLimit]     = useState(252)
  const [btLoading,   setBtLoading]   = useState(false)
  const [btResult,    setBtResult]    = useState<BacktestResult | null>(null)
  const [btError,     setBtError]     = useState<string | null>(null)

  useEffect(() => {
    api.getStrategy(id)
      .then((s) => {
        setStrategy(s)
        setBtSymbol(s.symbols[0] ?? 'SPY')
        setBtTimeframe(normalizeTimeframe(s.timeframe))
      })
      .catch(() => router.push('/'))
      .finally(() => setLoading(false))
  }, [id, router])

  async function handleRun() {
    if (!strategy) return
    setRunning(true)
    try {
      const run = await api.runStrategy(strategy.id, true)
      setLastRun(run)
      setTimeout(() => setRunning(false), 30_000)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Run failed')
      setRunning(false)
    }
  }

  async function handleBacktest() {
    if (!strategy) return
    setBtLoading(true)
    setBtError(null)
    setBtResult(null)
    try {
      const result = await api.runBacktest(strategy.id, {
        symbol: btSymbol.toUpperCase(),
        exchange: 'NASDAQ',
        timeframe: btTimeframe,
        limit: btLimit,
        initial_equity: 10_000,
      })
      setBtResult(result)
    } catch (e: unknown) {
      setBtError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setBtLoading(false)
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
  const m = btResult?.metrics

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

        {/* ── Body ────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Left — code + terminal + backtest */}
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

            {/* ── Backtest ──────────────────────────────────────────────── */}
            <GlassCard padding="none" className="overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-4 border-b border-zinc-100 dark:border-white/[0.05]">
                <FlaskConical className="w-4 h-4 text-amber-500" />
                <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
                  Backtest
                </span>
                <span className="ml-auto text-[10px] text-zinc-400">fills at next-bar open · no lookahead</span>
              </div>

              <div className="p-5 space-y-4">
                {/* Controls */}
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Symbol</label>
                    <input
                      value={btSymbol}
                      onChange={(e) => setBtSymbol(e.target.value)}
                      className="w-28 px-3 py-2 rounded-xl text-sm font-mono font-bold
                        bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800
                        text-zinc-900 dark:text-zinc-100 uppercase focus:outline-none
                        focus:ring-2 focus:ring-amber-400/40 transition"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Timeframe</label>
                    <select
                      value={btTimeframe}
                      onChange={(e) => setBtTimeframe(e.target.value)}
                      className="px-3 py-2 rounded-xl text-sm font-medium
                        bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800
                        text-zinc-900 dark:text-zinc-100 focus:outline-none
                        focus:ring-2 focus:ring-amber-400/40 transition cursor-pointer"
                    >
                      {['1d','4h','1h','15m','5m'].map(tf => (
                        <option key={tf} value={tf} className="dark:bg-zinc-900">{tf}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Bars</label>
                    <select
                      value={btLimit}
                      onChange={(e) => setBtLimit(Number(e.target.value))}
                      className="px-3 py-2 rounded-xl text-sm font-medium
                        bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800
                        text-zinc-900 dark:text-zinc-100 focus:outline-none
                        focus:ring-2 focus:ring-amber-400/40 transition cursor-pointer"
                    >
                      {[63, 126, 252, 504, 756].map(n => (
                        <option key={n} value={n} className="dark:bg-zinc-900">{n} bars</option>
                      ))}
                    </select>
                  </div>
                  <Button
                    onClick={handleBacktest}
                    loading={btLoading}
                    disabled={btLoading || !strategy.generated_logic || strategy.generated_logic.trim().length < 30}
                    className="ml-auto"
                    size="sm"
                  >
                    {!btLoading && <BarChart3 className="w-3.5 h-3.5 mr-1.5" />}
                    {btLoading ? 'Running…' : 'Run Backtest'}
                  </Button>
                </div>

                {!strategy.generated_logic || strategy.generated_logic.trim().length < 30 ? (
                  <p className="text-xs text-zinc-400 italic">
                    No compiled strategy code yet — create the strategy with AI Generate mode to unlock backtesting.
                  </p>
                ) : null}

                {/* Error */}
                {btError && (
                  <div className="px-4 py-3 rounded-xl bg-rose-50/80 dark:bg-rose-500/10
                    border border-rose-200 dark:border-rose-500/20
                    text-sm font-medium text-rose-600 dark:text-rose-400">
                    {btError}
                  </div>
                )}

                {/* Results */}
                {btResult && m && (
                  <div className="space-y-4 pt-1 animate-slide-up">
                    {/* Metrics grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <MetricTile
                        label="Total Return"
                        value={`${m.total_return_pct >= 0 ? '+' : ''}${m.total_return_pct.toFixed(2)}%`}
                        sub={`$${m.initial_equity.toLocaleString()} → $${m.final_equity.toLocaleString()}`}
                        up={m.total_return_pct >= 0}
                      />
                      <MetricTile
                        label="Sharpe Ratio"
                        value={m.sharpe_ratio.toFixed(3)}
                        sub={m.sharpe_ratio >= 1 ? 'Good' : m.sharpe_ratio >= 0.5 ? 'OK' : 'Weak'}
                        up={m.sharpe_ratio >= 1 ? true : m.sharpe_ratio >= 0 ? undefined : false}
                      />
                      <MetricTile
                        label="Max Drawdown"
                        value={`-${m.max_drawdown_pct.toFixed(2)}%`}
                        up={false}
                      />
                      <MetricTile
                        label="Win Rate"
                        value={`${m.win_rate_pct.toFixed(1)}%`}
                        sub={`${m.profitable_trades}/${m.total_trades} trades`}
                        up={m.win_rate_pct >= 50}
                      />
                    </div>

                    {/* Equity curve */}
                    <div className="rounded-xl overflow-hidden border border-zinc-100 dark:border-zinc-800
                      bg-zinc-950/5 dark:bg-zinc-900/40">
                      <EquityCurve data={btResult.equity_curve} initial={m.initial_equity} />
                    </div>

                    {/* Footer */}
                    <div className="flex items-center gap-4 text-[11px] text-zinc-400 font-medium">
                      <span className="flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        {btResult.bars_processed} bars · {btResult.symbol} · {btResult.timeframe}
                      </span>
                      <span>
                        {m.total_return_pct >= 0
                          ? <TrendingUp className="w-3.5 h-3.5 inline text-emerald-500 mr-0.5" />
                          : <TrendingDown className="w-3.5 h-3.5 inline text-rose-500 mr-0.5" />
                        }
                        {m.total_trades} fills · fills at next-bar open
                      </span>
                    </div>
                  </div>
                )}
              </div>
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

          {/* Right — risk + meta */}
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
