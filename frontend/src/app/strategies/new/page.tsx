'use client'
import { useState, useRef, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import { TIMEFRAMES } from '@/lib/constants'
import { X, Search, Brain, Code2, ShieldAlert, Activity, Zap, Clock, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { LLMConfig, TickerSearchResult } from '@/lib/types'

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), { ssr: false })

const QUANT_TEMPLATE = `# RestrictedPython sandbox — no imports needed.
# Pre-injected: BaseStrategy, OrderIntent, OrderSide, OrderType, Decimal, Optional


class MyStrategy(BaseStrategy):

    def on_bar(self) -> Optional[OrderIntent]:
        rsi      = self.indicators.get("RSI_14")
        ema_fast = self.indicators.get("EMA_20")
        ema_slow = self.indicators.get("EMA_50")

        if rsi is None or ema_fast is None or ema_slow is None:
            return None

        close = self.close
        qty   = Decimal(str(max(1, int(float(self.ctx.risk.max_order_notional) / close))))

        # Entry: RSI oversold in an uptrend
        if rsi < 30 and ema_fast > ema_slow and self.is_flat:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id,
                symbol=self.ctx.symbol,
                exchange=self.ctx.exchange,
                side=OrderSide.buy,
                quantity=qty,
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )

        # Respect risk config stop-loss / take-profit thresholds
        if self.is_long and self.avg_cost is not None:
            sl = self.ctx.risk.stop_loss_pct
            tp = self.ctx.risk.take_profit_pct
            pnl_pct = (close - self.avg_cost) / self.avg_cost * 100
            if (sl is not None and pnl_pct <= -float(sl)) or \\
               (tp is not None and pnl_pct >= float(tp)):
                return OrderIntent(
                    strategy_id=self.ctx.strategy_id, symbol=self.ctx.symbol,
                    exchange=self.ctx.exchange, side=OrderSide.sell,
                    quantity=Decimal(str(abs(self.position))),
                    order_type=OrderType.market,
                    estimated_price=Decimal(str(close)),
                    is_paper=self.ctx.risk.paper_trading_only,
                )

        # RSI overbought exit
        if rsi > 70 and self.is_long:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id, symbol=self.ctx.symbol,
                exchange=self.ctx.exchange, side=OrderSide.sell,
                quantity=Decimal(str(abs(self.position))),
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )

        return None
`

type Mode = 'nl' | 'quant'

function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <Icon className="w-3.5 h-3.5 text-violet-500 dark:text-violet-400" />
      <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-zinc-500 dark:text-zinc-500">
        {label}
      </span>
    </div>
  )
}

function FieldInput({
  label, helper, prefix, suffix, value, onChange, type = 'number',
  min, max, step, placeholder, required,
}: {
  label: string; helper: string; prefix?: string; suffix?: string
  value: string | number; onChange: (v: string) => void
  type?: string; min?: number; max?: number; step?: number
  placeholder?: string; required?: boolean
}) {
  return (
    <div>
      <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em] mb-2">
        {label}
      </label>
      <div className="relative">
        {prefix && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[12px] font-bold text-zinc-400 pointer-events-none">
            {prefix}
          </span>
        )}
        <input
          type={type} value={value} onChange={e => onChange(e.target.value)}
          min={min} max={max} step={step} placeholder={placeholder} required={required}
          className={cn(
            'w-full text-[14px] font-medium tabular-nums',
            'bg-zinc-50 dark:bg-zinc-900/60',
            'border border-zinc-200 dark:border-zinc-800 rounded-xl',
            'py-2.5 text-zinc-900 dark:text-zinc-100',
            'placeholder:text-zinc-400/60',
            'focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400/50',
            'transition-all',
            prefix ? 'pl-7' : 'pl-3',
            suffix ? 'pr-10' : 'pr-3',
          )}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-bold text-zinc-400 pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-[10px] text-zinc-400">{helper}</p>
    </div>
  )
}

export default function NewStrategyPage() {
  const router = useRouter()

  // ── Signal ──────────────────────────────────────────────────────────────────
  const [mode, setMode]     = useState<Mode>('nl')
  const [prompt, setPrompt] = useState('')
  const [code, setCode]     = useState(QUANT_TEMPLATE)

  // ── Identity ─────────────────────────────────────────────────────────────
  const [name, setName]           = useState('')
  const [timeframe, setTimeframe] = useState('1d')

  // ── Universe ─────────────────────────────────────────────────────────────
  const [symbols, setSymbols]               = useState<string[]>(['SPY'])
  const [exchange, setExchange]             = useState<string>('NASDAQ')
  const [tickerQuery, setTickerQuery]       = useState('')
  const [tickerResults, setTickerResults]   = useState<TickerSearchResult[]>([])
  const [tickerLoading, setTickerLoading]   = useState(false)
  const [showDropdown, setShowDropdown]     = useState(false)
  const [dropdownIdx, setDropdownIdx]       = useState(-1)
  const searchRef      = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // ── Position Sizing ───────────────────────────────────────────────────────
  const [maxOrderNotional, setMaxOrderNotional]       = useState('1000')
  const [maxPositionNotional, setMaxPositionNotional] = useState('10000')
  const [maxOpenPositions, setMaxOpenPositions]       = useState('5')

  // ── Risk Controls ─────────────────────────────────────────────────────────
  const [maxDailyNotional, setMaxDailyNotional] = useState('50000')
  const [stopLossPct, setStopLossPct]           = useState('')  // '' = disabled
  const [takeProfitPct, setTakeProfitPct]       = useState('')  // '' = disabled

  // ── Execution Model ───────────────────────────────────────────────────────
  const [tradeSession, setTradeSession]             = useState<'regular' | 'extended'>('regular')
  const [slippageBps, setSlippageBps]               = useState('5')
  const [commissionPerShare, setCommissionPerShare] = useState('0.005')

  // ── Mode ──────────────────────────────────────────────────────────────────
  const [paperOnly, setPaperOnly] = useState(true)

  // ── LLM model selection (NL mode) ────────────────────────────────────────
  const [llmConfigs, setLlmConfigs]       = useState<LLMConfig[]>([])
  const [selectedLLM, setSelectedLLM]     = useState<string | null>(null) // null = platform default

  useEffect(() => {
    api.listLLMConfigs()
      .then((configs) => {
        setLlmConfigs(configs)
        // Auto-select the only user config if exactly one exists
        if (configs.length === 1) setSelectedLLM(configs[0].id)
      })
      .catch(() => {})
  }, [])

  // ── UI ────────────────────────────────────────────────────────────────────
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [editorTheme, setEditorTheme] = useState('vs-dark')

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    setEditorTheme(mq.matches ? 'vs-dark' : 'light')
    const h = (e: MediaQueryListEvent) => setEditorTheme(e.matches ? 'vs-dark' : 'light')
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])

  // Close dropdown on click-outside
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
        setDropdownIdx(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Debounced ticker search (250 ms)
  useEffect(() => {
    if (tickerQuery.length < 1) {
      setTickerResults([])
      setShowDropdown(false)
      return
    }
    const timer = setTimeout(async () => {
      setTickerLoading(true)
      try {
        const results = await api.searchTickers(tickerQuery)
        setTickerResults(results)
        setShowDropdown(results.length > 0)
        setDropdownIdx(-1)
      } catch {
        setTickerResults([])
        setShowDropdown(false)
      } finally {
        setTickerLoading(false)
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [tickerQuery])

  function addSymbol(sym: string, exch?: string) {
    let u = sym.toUpperCase().trim()
    if (!u) {
      setTickerQuery('')
      setShowDropdown(false)
      setDropdownIdx(-1)
      return
    }
    // Carry exchange info into the symbol so the backend correctly classifies
    // NSE/BSE strategies (yfinance requires the .NS / .BO suffix).
    const ex = (exch ?? exchange).toUpperCase()
    if (ex === 'NSE' && !u.endsWith('.NS')) u = `${u}.NS`
    else if (ex === 'BSE' && !u.endsWith('.BO')) u = `${u}.BO`

    if (!symbols.includes(u)) {
      setSymbols(p => [...p, u])
      if (symbols.length === 0 && exch) setExchange(ex)
    }
    setTickerQuery('')
    setShowDropdown(false)
    setDropdownIdx(-1)
  }

  function handleTickerKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showDropdown) {
      if (e.key === 'Enter' && tickerQuery.trim()) { e.preventDefault(); addSymbol(tickerQuery) }
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setDropdownIdx(i => Math.min(i + 1, tickerResults.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setDropdownIdx(i => Math.max(i - 1, -1)) }
    else if (e.key === 'Enter') {
      e.preventDefault()
      if (dropdownIdx >= 0 && tickerResults[dropdownIdx]) {
        const r = tickerResults[dropdownIdx]
        addSymbol(r.symbol, r.exchange)
      }
      else if (tickerQuery.trim()) addSymbol(tickerQuery)
    } else if (e.key === 'Escape') {
      setShowDropdown(false); setDropdownIdx(-1)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    let finalSymbols = [...symbols]
    let pending = tickerQuery.toUpperCase().trim()
    if (exchange === 'NSE' && !pending.endsWith('.NS')) pending = pending ? `${pending}.NS` : pending
    else if (exchange === 'BSE' && !pending.endsWith('.BO')) pending = pending ? `${pending}.BO` : pending
    if (pending && !finalSymbols.includes(pending)) {
      finalSymbols.push(pending)
      setSymbols(finalSymbols)
      setTickerQuery('')
    }

    if (finalSymbols.length === 0) { setError('Specify at least one instrument in the Execution Universe.'); return }
    if (mode === 'quant' && code.trim().length < 20) { setError('Strategy class body is empty.'); return }

    const orderCap    = parseFloat(maxOrderNotional) || 0
    const posCap      = parseFloat(maxPositionNotional) || 0
    const dailyCap    = parseFloat(maxDailyNotional) || 0
    const openPos     = parseInt(maxOpenPositions, 10) || 1
    const slippage    = parseInt(slippageBps, 10) || 0
    const commission  = parseFloat(commissionPerShare) || 0
    const stopLoss    = stopLossPct !== '' ? parseFloat(stopLossPct) : null
    const takeProfit  = takeProfitPct !== '' ? parseFloat(takeProfitPct) : null

    if (orderCap < 100) { setError('Per-fill notional cap must be ≥ $100.'); return }
    if (posCap < orderCap) { setError('Position cap must be ≥ per-fill cap.'); return }
    if (dailyCap < orderCap) { setError('Daily turnover cap must be ≥ per-fill cap.'); return }

    setLoading(true)
    setError(null)
    try {
      const s = await api.createStrategy({
        name,
        prompt: mode === 'nl' ? prompt : `[quant] ${name}`,
        symbols: finalSymbols,
        exchange,
        timeframe,
        risk: {
          max_order_notional:    orderCap,
          max_position_notional: posCap,
          max_open_positions:    openPos,
          max_daily_notional:    dailyCap,
          stop_loss_pct:         stopLoss,
          take_profit_pct:       takeProfit,
          slippage_bps:          slippage,
          commission_per_share:  commission,
          trade_session:         tradeSession,
          allowed_symbols:       finalSymbols,
          paper_trading_only:    paperOnly,
        },
        creation_mode: mode,
        ...(mode === 'quant' ? { code_source: code } : {}),
        ...(mode === 'nl' && selectedLLM ? { llm_config_id: selectedLLM } : {}),
      })
      router.push(`/strategies/${s.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Request failed')
      setLoading(false)
    }
  }

  const hasSymbols = symbols.length > 0 || tickerQuery.trim().length > 0
  const nlReady    = name.length >= 3 && prompt.length >= 10 && hasSymbols
  const quantReady = name.length >= 3 && code.trim().length >= 20 && hasSymbols
  const ready      = mode === 'nl' ? nlReady : quantReady

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto pb-24 relative z-10 animate-slide-up">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="mb-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-violet-600 dark:text-violet-400 mb-2">
            Strategy Builder
          </p>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">
            New Strategy
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Signal logic · execution universe · complete risk model
          </p>
        </div>

        {/* ── Mode toggle ────────────────────────────────────────────────── */}
        <div className="flex gap-2 mb-6 p-1 bg-zinc-100 dark:bg-zinc-900/80 rounded-xl border border-zinc-200 dark:border-zinc-800">
          {([
            { id: 'nl' as const, Icon: Brain, label: 'AI Generated', sub: 'Describe in English — AI writes the class' },
            { id: 'quant' as const, Icon: Code2, label: 'Python Class', sub: 'Write a BaseStrategy subclass directly' },
          ]).map(({ id, Icon, label, sub }) => (
            <button key={id} type="button" onClick={() => setMode(id)}
              className={cn(
                'flex-1 flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all duration-150',
                mode === id
                  ? 'bg-white dark:bg-zinc-800 shadow-sm border border-zinc-200 dark:border-zinc-700'
                  : 'hover:bg-white/50 dark:hover:bg-zinc-800/40',
              )}>
              <Icon className={cn('w-4 h-4 flex-shrink-0', mode === id ? 'text-violet-600 dark:text-violet-400' : 'text-zinc-400')} />
              <div>
                <div className={cn('text-[13px] font-semibold leading-tight', mode === id ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-500')}>
                  {label}
                </div>
                <div className="text-[11px] text-zinc-400 mt-0.5">{sub}</div>
              </div>
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">

          {/* ── Alpha Thesis (NL) ──────────────────────────────────────────── */}
          {mode === 'nl' && (
            <GlassCard padding="none" className="overflow-hidden">
              <div className="px-5 pt-5 pb-3">
                <div className="flex items-baseline justify-between mb-3">
                  <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em]">
                    Alpha Thesis
                  </label>
                  <span className="text-[10px] text-zinc-400 tabular-nums">{prompt.length} / 4000</span>
                </div>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={'"When RSI(14) drops below 28 and price is above EMA(200), enter long. Size the position using a fraction of the notional cap. Exit when RSI exceeds 72 or a 2% trailing stop is triggered."'}
                  className="w-full min-h-[196px] text-[14px] leading-relaxed resize-none bg-transparent text-zinc-800 dark:text-zinc-100 placeholder:text-zinc-400/60 dark:placeholder:text-zinc-600 focus:outline-none"
                  required={mode === 'nl'}
                  minLength={10}
                  maxLength={4000}
                />
              </div>
              {/* Model selector row */}
              <div className="flex items-center gap-3 px-5 py-3 bg-zinc-50/50 dark:bg-zinc-900/40 border-t border-black/[0.04] dark:border-white/[0.04]">
                <Brain className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0" />
                <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest whitespace-nowrap">Model</span>
                <select
                  value={selectedLLM ?? ''}
                  onChange={(e) => setSelectedLLM(e.target.value || null)}
                  className="flex-1 min-w-0 bg-transparent text-[12px] font-medium text-zinc-700 dark:text-zinc-300 focus:outline-none cursor-pointer"
                >
                  <option value="">Platform Default (Free · Groq llama-3.1-8b-instant)</option>
                  {llmConfigs.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} · {c.model}
                    </option>
                  ))}
                </select>
                {llmConfigs.length === 0 && (
                  <a href="/settings/ai" className="text-[10px] font-semibold text-violet-500 hover:text-violet-600 whitespace-nowrap">
                    + Add key
                  </a>
                )}
              </div>
              <div className="flex items-center gap-2 px-5 py-3 bg-zinc-50/50 dark:bg-zinc-900/40 border-t border-black/[0.04] dark:border-white/[0.04]">
                <span className="text-[10px] text-zinc-400">
                  Pre-computed: RSI · MACD · EMA(20/50/200) · BB(20) · ATR(14) · VWAP
                </span>
                {prompt.length >= 10 && (
                  <span className="ml-auto flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    Ready to compile
                  </span>
                )}
              </div>
            </GlassCard>
          )}

          {/* ── Python class editor ────────────────────────────────────────── */}
          {mode === 'quant' && (
            <GlassCard padding="none" className="overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-black/[0.04] dark:border-white/[0.04] bg-zinc-50/60 dark:bg-zinc-900/60">
                <div className="flex items-center gap-2">
                  <Code2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em]">Strategy Class</span>
                </div>
                <span className="text-[10px] font-medium text-zinc-400">RestrictedPython sandbox · no network · no fs</span>
              </div>
              <div style={{ height: 420 }}>
                <MonacoEditor height="420px" language="python" theme={editorTheme} value={code}
                  onChange={val => setCode(val ?? '')}
                  options={{
                    fontSize: 13,
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    minimap: { enabled: false }, lineNumbers: 'on',
                    scrollBeyondLastLine: false, wordWrap: 'on',
                    padding: { top: 14, bottom: 14 }, tabSize: 4,
                    renderLineHighlight: 'gutter',
                    scrollbar: { vertical: 'auto', horizontal: 'hidden' },
                  }}
                />
              </div>
              <div className="px-5 py-2.5 bg-zinc-50/40 dark:bg-zinc-900/40 border-t border-black/[0.04] dark:border-white/[0.04]">
                <p className="text-[11px] text-zinc-400">
                  Extend{' '}<code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1 rounded text-[10px]">BaseStrategy</code>
                  {' '}· implement{' '}<code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1 rounded text-[10px]">on_bar() → Optional[OrderIntent]</code>
                  {' '}· access risk config via{' '}<code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1 rounded text-[10px]">self.ctx.risk</code>
                </p>
              </div>
            </GlassCard>
          )}

          {/* ── Identity ───────────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <GlassCard padding="lg">
              <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em] mb-3">
                Identifier
              </label>
              <input
                type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="RSI_MeanRev_1D" required minLength={3} maxLength={120}
                className="w-full bg-transparent text-[14px] font-medium text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400/50 dark:placeholder:text-zinc-600 focus:outline-none"
              />
              <p className="mt-2 text-[10px] text-zinc-400">Slug-style name, unique per tenant</p>
            </GlassCard>

            <GlassCard padding="lg">
              <label className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em] mb-3">
                <Activity className="w-3 h-3 text-violet-500" />
                Bar Resolution
              </label>
              <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
                className="w-full bg-transparent text-[14px] font-medium text-zinc-900 dark:text-zinc-100 focus:outline-none cursor-pointer">
                {TIMEFRAMES.map(tf => (
                  <option key={tf.value} value={tf.value} className="dark:bg-zinc-900">{tf.label}</option>
                ))}
              </select>
              <p className="mt-2 text-[10px] text-zinc-400">OHLCV interval for signal computation</p>
            </GlassCard>
          </div>

          {/* ── Execution Universe ─────────────────────────────────────────── */}
          <GlassCard padding="lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-3.5 h-3.5 text-violet-500" />
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em]">Execution Universe</span>
              </div>
              <span className="text-[10px] font-mono text-zinc-400">
                {symbols.length} instrument{symbols.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Exchange / Asset class */}
            <div className="mb-4">
              <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em] mb-2">
                Exchange / Asset Class
              </label>
              <div className="flex gap-1.5 flex-wrap">
                {(['NASDAQ', 'NYSE', 'NSE', 'BSE', 'CRYPTO'] as const).map(ex => (
                  <button key={ex} type="button" onClick={() => setExchange(ex)}
                    className={cn(
                      'px-3 py-1.5 rounded-lg text-[11px] font-bold font-mono border transition-all',
                      exchange === ex
                        ? 'bg-violet-600 dark:bg-violet-500 border-violet-600 dark:border-violet-500 text-white'
                        : 'bg-zinc-50 dark:bg-zinc-900/60 border-zinc-200 dark:border-zinc-800 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100',
                    )}>
                    {ex}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-[10px] text-zinc-400">
                Auto-detected from ticker search — override for manually typed symbols (e.g. NSE/BSE need
                a <code className="font-mono">.NS</code> / <code className="font-mono">.BO</code> suffix, applied automatically).
              </p>
            </div>

            {/* Selected symbols */}
            {symbols.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mb-3">
                {symbols.map(sym => (
                  <button key={sym} type="button" onClick={() => setSymbols(p => p.filter(s => s !== sym))}
                    className="inline-flex items-center gap-1 text-[11px] font-bold font-mono px-2.5 py-1 rounded-md
                      bg-violet-50 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300
                      border border-violet-200 dark:border-violet-500/30
                      hover:bg-rose-50 dark:hover:bg-rose-500/15 hover:text-rose-600 dark:hover:text-rose-400
                      hover:border-rose-200 dark:hover:border-rose-500/30 transition-colors">
                    {sym} <X className="w-3 h-3" />
                  </button>
                ))}
              </div>
            )}

            {/* Ticker search with autocomplete */}
            <div ref={searchRef} className="relative">
              <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl
                bg-zinc-50 dark:bg-zinc-900/60
                border border-zinc-200 dark:border-zinc-700
                focus-within:border-violet-400/60 dark:focus-within:border-violet-500/50
                focus-within:ring-2 focus-within:ring-violet-500/10 transition-all">
                {tickerLoading
                  ? <span className="w-3.5 h-3.5 rounded-full border-2 border-zinc-300 dark:border-zinc-600 border-t-violet-500 animate-spin flex-shrink-0" />
                  : <Search className="w-3.5 h-3.5 text-zinc-400 flex-shrink-0" />
                }
                <input
                  ref={searchInputRef} type="text" value={tickerQuery}
                  onChange={e => setTickerQuery(e.target.value)}
                  onKeyDown={handleTickerKeyDown}
                  onFocus={() => tickerQuery.length > 0 && tickerResults.length > 0 && setShowDropdown(true)}
                  placeholder="Search by ticker or company name…"
                  className="flex-1 bg-transparent text-[13px] font-medium text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400/60 focus:outline-none"
                />
                {tickerQuery && (
                  <button type="button" onClick={() => { setTickerQuery(''); setShowDropdown(false) }}
                    className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 flex-shrink-0">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Dropdown */}
              {showDropdown && tickerResults.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1.5 z-50
                  bg-white dark:bg-zinc-900
                  border border-zinc-200 dark:border-zinc-700
                  rounded-xl shadow-xl dark:shadow-black/50 overflow-hidden">
                  {tickerResults.map((r, i) => (
                    <button key={`${r.symbol}-${r.exchange}-${i}`} type="button" onClick={() => addSymbol(r.symbol, r.exchange)}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors',
                        i === dropdownIdx
                          ? 'bg-violet-50 dark:bg-violet-500/15'
                          : 'hover:bg-zinc-50 dark:hover:bg-zinc-800',
                      )}>
                      <span className="text-[13px] font-bold font-mono text-zinc-900 dark:text-zinc-100 w-20 flex-shrink-0">
                        {r.symbol}
                      </span>
                      <span className="text-[12px] text-zinc-500 dark:text-zinc-400 truncate flex-1">
                        {r.name}
                      </span>
                      <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded
                        bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 flex-shrink-0">
                        {r.exchange}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Quick-add suggestions */}
            <div className="flex gap-1.5 flex-wrap items-center pt-3 mt-2 border-t border-black/[0.04] dark:border-white/[0.04]">
              <span className="text-[10px] text-zinc-400 mr-1">Quick add</span>
              {['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'JPM', 'GS']
                .filter(s => !symbols.includes(s))
                .map(sym => (
                  <button key={sym} type="button" onClick={() => addSymbol(sym, 'NASDAQ')}
                    className="text-[11px] font-bold font-mono px-2.5 py-1 rounded-md
                      bg-zinc-100 dark:bg-zinc-800/60 text-zinc-500
                      hover:bg-zinc-200 dark:hover:bg-zinc-700 hover:text-zinc-900 dark:hover:text-zinc-100
                      transition-colors">
                    + {sym}
                  </button>
                ))}
            </div>
          </GlassCard>

          {/* ── Position Sizing ────────────────────────────────────────────── */}
          <GlassCard padding="lg">
            <SectionHeader icon={Zap} label="Position Sizing" />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FieldInput
                label="Per-Fill Cap" helper="Max notional per single fill" prefix="$"
                value={maxOrderNotional} onChange={setMaxOrderNotional}
                min={100} max={1_000_000} step={100}
              />
              <FieldInput
                label="Position Cap" helper="Max total exposure per instrument" prefix="$"
                value={maxPositionNotional} onChange={setMaxPositionNotional}
                min={500} max={10_000_000} step={500}
              />
              <FieldInput
                label="Max Positions" helper="Concurrent open positions across the universe"
                value={maxOpenPositions} onChange={setMaxOpenPositions}
                min={1} max={100} step={1}
              />
            </div>
          </GlassCard>

          {/* ── Risk Controls ──────────────────────────────────────────────── */}
          <GlassCard padding="lg">
            <SectionHeader icon={ShieldAlert} label="Risk Controls" />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FieldInput
                label="Daily Turnover Cap" helper="Gross buy+sell notional per session" prefix="$"
                value={maxDailyNotional} onChange={setMaxDailyNotional}
                min={1000} max={100_000_000} step={1000}
              />
              <FieldInput
                label="Stop-Loss" helper="Hard stop per position — blank to disable" suffix="%"
                value={stopLossPct} onChange={setStopLossPct}
                min={0.1} max={99} step={0.1} placeholder="Off"
              />
              <FieldInput
                label="Take-Profit" helper="Profit target per position — blank to disable" suffix="%"
                value={takeProfitPct} onChange={setTakeProfitPct}
                min={0.1} max={10000} step={0.1} placeholder="Off"
              />
            </div>
          </GlassCard>

          {/* ── Execution Model ────────────────────────────────────────────── */}
          <GlassCard padding="lg">
            <SectionHeader icon={Clock} label="Execution Model" />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">

              {/* Trade session */}
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-[0.12em] mb-2">
                  Trade Session
                </label>
                <div className="flex gap-2">
                  {(['regular', 'extended'] as const).map(s => (
                    <button key={s} type="button" onClick={() => setTradeSession(s)}
                      className={cn(
                        'flex-1 py-2.5 rounded-xl text-[12px] font-semibold border transition-all',
                        tradeSession === s
                          ? 'bg-violet-600 dark:bg-violet-500 border-violet-600 dark:border-violet-500 text-white'
                          : 'bg-zinc-50 dark:bg-zinc-900/60 border-zinc-200 dark:border-zinc-800 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100',
                      )}>
                      {s === 'regular' ? 'Regular' : 'Extended'}
                    </button>
                  ))}
                </div>
                <p className="mt-1.5 text-[10px] text-zinc-400">Regular: 09:30–16:00 ET only</p>
              </div>

              <FieldInput
                label="Slippage" helper="Assumed market impact for cost modeling" suffix="bps"
                value={slippageBps} onChange={setSlippageBps}
                min={0} max={500} step={1}
              />
              <FieldInput
                label="Commission" helper="Per-share execution cost model" prefix="$" suffix="/sh"
                value={commissionPerShare} onChange={setCommissionPerShare}
                min={0} max={1} step={0.001}
              />
            </div>
          </GlassCard>

          {/* ── Trading Mode ───────────────────────────────────────────────── */}
          <GlassCard padding="lg">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[13px] font-semibold text-zinc-800 dark:text-zinc-200">
                  {paperOnly ? 'Paper Trading' : 'Live Trading'}
                </p>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  {paperOnly
                    ? 'All orders are simulated — no real capital at risk'
                    : 'Real orders will be placed through your connected broker'}
                </p>
              </div>
              <button type="button" onClick={() => setPaperOnly(p => !p)}
                className={cn(
                  'relative w-12 h-6 rounded-full transition-colors duration-200 flex-shrink-0',
                  paperOnly ? 'bg-zinc-200 dark:bg-zinc-700' : 'bg-rose-500',
                )}>
                <span className={cn(
                  'absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200',
                  paperOnly ? 'translate-x-1' : 'translate-x-7',
                )} />
              </button>
            </div>
            <div className={cn(
              'mt-3 flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border',
              paperOnly
                ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20'
                : 'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/25',
            )}>
              <ShieldAlert className={cn('w-3.5 h-3.5 flex-shrink-0 mt-0.5', paperOnly ? 'text-emerald-500' : 'text-rose-500')} />
              <p className={cn('text-[12px] font-medium', paperOnly ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300')}>
                {paperOnly
                  ? 'Paper mode — simulated execution with real market data'
                  : 'Live trading active. Confirm broker connection and risk parameters before running.'}
              </p>
            </div>
          </GlassCard>

          {/* ── Error ──────────────────────────────────────────────────────── */}
          {error && (
            <div className="px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-500/10
              border border-rose-200 dark:border-rose-500/20
              text-[13px] font-medium text-rose-600 dark:text-rose-400">
              {error}
            </div>
          )}

          {/* ── Submit ─────────────────────────────────────────────────────── */}
          <div className="pt-2">
            <Button type="submit" size="lg" className="w-full h-12 text-[14px] font-bold tracking-wide"
              loading={loading} disabled={!ready}>
              {loading
                ? (mode === 'nl' ? 'Compiling signal…' : 'Deploying agent…')
                : (mode === 'nl' ? 'Compile & Deploy Agent' : 'Deploy Python Agent')}
            </Button>
          </div>

        </form>
      </div>
    </AppShell>
  )
}
