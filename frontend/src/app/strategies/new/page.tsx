'use client'
import { useState, useRef, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import { TIMEFRAMES, DEFAULT_SYMBOLS } from '@/lib/constants'
import { X, ChevronDown, ChevronUp, Sparkles, Activity, ShieldAlert, Cpu, Code2, Brain } from 'lucide-react'
import { cn } from '@/lib/utils'

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), { ssr: false })

const QUANT_TEMPLATE = `from alphaswarm.strategy import BaseStrategy, StrategyContext, Signal


class MyStrategy(BaseStrategy):
    """
    Quant strategy — runs as an isolated worker on AlphaSwarm.
    Implement on_bar() to emit buy/sell signals each tick.
    All capital stays in your own broker account.
    """

    def __init__(self):
        super().__init__()
        self.rsi_period = 14
        self.ema_fast = 20
        self.ema_slow = 50

    def on_bar(self, ctx: StrategyContext) -> Signal | None:
        """
        Called on every new bar for each configured symbol.
        Return Signal.BUY, Signal.SELL, or None to hold.

        ctx.bars(limit=n)       -> list[Bar]  (OHLCV, Decimal prices)
        ctx.indicator("rsi_14") -> float | None
        ctx.symbol              -> str  e.g. "AAPL"
        ctx.timeframe           -> str  e.g. "1Min"
        """
        bars = ctx.bars(limit=self.rsi_period + 1)
        if len(bars) < self.rsi_period:
            return None  # Not enough history yet

        rsi     = ctx.indicator(f"rsi_{self.rsi_period}")
        ema_fast = ctx.indicator(f"ema_{self.ema_fast}")
        ema_slow = ctx.indicator(f"ema_{self.ema_slow}")
        close   = float(bars[-1].close)

        # Trend filter: only buy when fast EMA > slow EMA
        uptrend = (ema_fast is not None and ema_slow is not None
                   and ema_fast > ema_slow)

        if rsi is not None and rsi < 30 and uptrend:
            return Signal.BUY   # Oversold in an uptrend

        if rsi is not None and rsi > 70:
            return Signal.SELL  # Overbought — exit

        return None  # Hold
`

type Mode = 'nl' | 'quant'

export default function NewStrategyPage() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('nl')
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [code, setCode] = useState(QUANT_TEMPLATE)
  const [symbols, setSymbols] = useState<string[]>(['SPY'])
  const [timeframe, setTimeframe] = useState('1Min')
  const [showRisk, setShowRisk] = useState(false)
  const [maxOrder, setMaxOrder] = useState(1000)
  const [maxDaily, setMaxDaily] = useState(5000)
  const [symbolInput, setSymbolInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const symbolInputRef = useRef<HTMLInputElement>(null)

  // Keep Monaco theme in sync with system dark mode
  const [editorTheme, setEditorTheme] = useState('vs-dark')
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    setEditorTheme(mq.matches ? 'vs-dark' : 'light')
    const handler = (e: MediaQueryListEvent) => setEditorTheme(e.matches ? 'vs-dark' : 'light')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  function addSymbol(sym: string) {
    const u = sym.toUpperCase().trim()
    if (u && !symbols.includes(u)) setSymbols((prev) => [...prev, u])
    setSymbolInput('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    let finalSymbols = [...symbols]
    const pendingSymbol = symbolInput.toUpperCase().trim()
    if (pendingSymbol && !symbols.includes(pendingSymbol)) {
      finalSymbols.push(pendingSymbol)
      setSymbols(finalSymbols)
      setSymbolInput('')
    }

    if (finalSymbols.length === 0) {
      setError('Add at least one symbol to trade.')
      return
    }

    if (mode === 'quant' && code.trim().length < 20) {
      setError('Your strategy code looks empty.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const s = await api.createStrategy({
        name,
        prompt: mode === 'nl' ? prompt : `[quant] ${name}`,
        symbols: finalSymbols,
        timeframe,
        risk: { max_order_notional: maxOrder, max_daily_notional: maxDaily, allowed_symbols: finalSymbols, paper_trading_only: true },
        creation_mode: mode,
        ...(mode === 'quant' ? { code_source: code } : {}),
      })
      router.push(`/strategies/${s.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setLoading(false)
    }
  }

  const nlReady = name.length >= 3 && prompt.length >= 10 && (symbols.length > 0 || symbolInput.trim().length > 0)
  const quantReady = name.length >= 3 && code.trim().length >= 20 && (symbols.length > 0 || symbolInput.trim().length > 0)
  const ready = mode === 'nl' ? nlReady : quantReady

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto animate-slide-up relative z-10 pb-20">
        {/* Header */}
        <div className="mb-8 flex flex-col items-center text-center">
          <h2 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-600 dark:from-white dark:to-zinc-400 tracking-tight mb-3">
            Build Your Strategy
          </h2>
          <p className="text-base text-zinc-500 dark:text-zinc-400 max-w-lg leading-relaxed">
            Describe it in plain English or write Python directly — AlphaSwarm deploys it as a live trading agent.
          </p>
        </div>

        {/* Mode Toggle */}
        <div className="flex gap-3 mb-8 p-1.5 bg-zinc-100 dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800">
          <button
            type="button"
            onClick={() => setMode('nl')}
            className={cn(
              'flex-1 flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl text-sm font-semibold transition-all duration-200',
              mode === 'nl'
                ? 'bg-white dark:bg-zinc-800 text-violet-700 dark:text-violet-400 shadow-sm border border-violet-200 dark:border-violet-500/30'
                : 'text-zinc-500 dark:text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300',
            )}
          >
            <Brain className="w-4 h-4" />
            AI Generate
            <span className={cn(
              'text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide',
              mode === 'nl' ? 'bg-violet-100 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400' : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-400',
            )}>
              No code
            </span>
          </button>
          <button
            type="button"
            onClick={() => setMode('quant')}
            className={cn(
              'flex-1 flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl text-sm font-semibold transition-all duration-200',
              mode === 'quant'
                ? 'bg-white dark:bg-zinc-800 text-emerald-700 dark:text-emerald-400 shadow-sm border border-emerald-200 dark:border-emerald-500/30'
                : 'text-zinc-500 dark:text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300',
            )}
          >
            <Code2 className="w-4 h-4" />
            Write Code
            <span className={cn(
              'text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide',
              mode === 'quant' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400' : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-400',
            )}>
              Python
            </span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* NL Mode: prose textarea */}
          {mode === 'nl' && (
            <GlassCard padding="none" className="overflow-hidden group focus-within:ring-2 focus-within:ring-violet-500/30 transition-all duration-300">
              <div className="px-6 pt-5 pb-2">
                <label className="flex items-center gap-2 text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-3">
                  <Sparkles className="w-4 h-4 text-violet-500" /> Trading Logic
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder={`"Buy SPY when the 5-min RSI drops below 30 and the MACD line crosses above the signal line. Hard stop-loss at 2% below entry price, take profit at 5%."`}
                  className="w-full min-h-[220px] text-[15px] leading-relaxed resize-none bg-transparent text-zinc-800 dark:text-zinc-100 placeholder:text-zinc-400/60 dark:placeholder:text-zinc-600/70 focus:outline-none"
                  required={mode === 'nl'}
                  minLength={10}
                  maxLength={4000}
                />
              </div>
              <div className="flex items-center justify-between px-6 py-4 bg-zinc-50/50 dark:bg-zinc-900/50 border-t border-black/[0.05] dark:border-white/[0.05]">
                <span className="text-xs font-medium text-zinc-400">{prompt.length} / 4000</span>
                {prompt.length >= 10 && <Badge variant="success" dot className="animate-fade-in shadow-sm">Ready to compile</Badge>}
              </div>
            </GlassCard>
          )}

          {/* Quant Mode: Monaco editor */}
          {mode === 'quant' && (
            <GlassCard padding="none" className="overflow-hidden border-emerald-200/50 dark:border-emerald-500/20">
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-black/[0.05] dark:border-white/[0.05] bg-zinc-50/80 dark:bg-zinc-900/80">
                <div className="flex items-center gap-2">
                  <Code2 className="w-4 h-4 text-emerald-500" />
                  <span className="text-xs font-bold text-zinc-600 dark:text-zinc-400 uppercase tracking-widest">Python Strategy</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">Sandbox isolated</span>
                </div>
              </div>
              <div className="rounded-b-2xl overflow-hidden" style={{ height: 420 }}>
                <MonacoEditor
                  height="420px"
                  language="python"
                  theme={editorTheme}
                  value={code}
                  onChange={(val) => setCode(val ?? '')}
                  options={{
                    fontSize: 13,
                    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
                    minimap: { enabled: false },
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    padding: { top: 16, bottom: 16 },
                    tabSize: 4,
                    renderLineHighlight: 'gutter',
                    scrollbar: { vertical: 'hidden', horizontal: 'hidden' },
                  }}
                />
              </div>
              <div className="px-5 py-3 bg-zinc-50/50 dark:bg-zinc-900/50 border-t border-black/[0.05] dark:border-white/[0.05]">
                <p className="text-xs text-zinc-400 dark:text-zinc-500">
                  Your class must extend <code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1 rounded">BaseStrategy</code> and implement <code className="font-mono bg-zinc-100 dark:bg-zinc-800 px-1 rounded">on_bar(ctx)</code>. Code runs in a RestrictedPython sandbox — no network, no filesystem.
                </p>
              </div>
            </GlassCard>
          )}

          {/* Name + Timeframe */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <GlassCard padding="lg" className="focus-within:ring-2 focus-within:ring-violet-500/30 transition-all duration-300">
              <label className="flex items-center gap-2 text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-4">
                Strategy Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Mean Reversion Alpha"
                required
                minLength={3}
                maxLength={120}
                className="w-full bg-transparent text-[15px] font-medium text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none"
              />
            </GlassCard>

            <GlassCard padding="lg" className="focus-within:ring-2 focus-within:ring-violet-500/30 transition-all duration-300">
              <label className="flex items-center gap-2 text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-4">
                <Activity className="w-4 h-4 text-violet-500" /> Resolution
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-transparent text-[15px] font-medium text-zinc-900 dark:text-zinc-100 focus:outline-none cursor-pointer appearance-none"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value} className="dark:bg-zinc-900">{tf.label}</option>
                ))}
              </select>
            </GlassCard>
          </div>

          {/* Symbols */}
          <GlassCard padding="lg" className="focus-within:ring-2 focus-within:ring-violet-500/30 transition-all duration-300">
            <label className="flex items-center gap-2 text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-4">
              Target Assets
            </label>
            <div className="flex flex-wrap items-center gap-2.5 mb-5">
              {symbols.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => setSymbols((p) => p.filter((s) => s !== sym))}
                  className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300 hover:bg-rose-100 hover:text-rose-600 dark:hover:bg-rose-500/20 dark:hover:text-rose-400 transition-colors shadow-sm"
                >
                  {sym}<X className="w-3.5 h-3.5" />
                </button>
              ))}
              <input
                ref={symbolInputRef}
                type="text"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    if (symbolInput.trim()) addSymbol(symbolInput)
                  }
                }}
                onBlur={() => { if (symbolInput.trim()) addSymbol(symbolInput) }}
                placeholder="Type ticker & press Enter…"
                className="text-sm font-medium bg-transparent focus:outline-none text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400/70 min-w-0 flex-1 ml-1"
              />
            </div>
            <div className="flex gap-2 flex-wrap pt-4 border-t border-black/[0.05] dark:border-white/[0.05]">
              {DEFAULT_SYMBOLS.filter((s) => !symbols.includes(s)).map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => { addSymbol(sym); symbolInputRef.current?.focus() }}
                  className="text-xs font-bold px-3 py-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800/80 text-zinc-500 hover:bg-zinc-200 dark:hover:bg-zinc-700 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors shadow-sm"
                >
                  + {sym}
                </button>
              ))}
            </div>
          </GlassCard>

          {/* Risk */}
          <GlassCard padding="none" className="overflow-hidden transition-all duration-300">
            <button
              type="button"
              onClick={() => setShowRisk(!showRisk)}
              className="w-full flex items-center justify-between px-6 py-5 text-[15px] font-bold text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors"
            >
              <span className="flex items-center gap-2"><ShieldAlert className="w-4 h-4 text-rose-500" /> Risk Management</span>
              {showRisk ? <ChevronUp className="w-5 h-5 text-zinc-400" /> : <ChevronDown className="w-5 h-5 text-zinc-400" />}
            </button>
            <div className={cn(
              'grid transition-all duration-300 ease-in-out',
              showRisk ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
            )}>
              <div className="overflow-hidden">
                <div className="px-6 pb-6 pt-2 border-t border-black/[0.05] dark:border-white/[0.05] space-y-6">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Max Position (USD)</label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 font-medium">$</span>
                        <input type="number" value={maxOrder} onChange={(e) => setMaxOrder(Number(e.target.value))} min={1} step={100}
                          className="w-full text-[15px] font-medium bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl pl-8 pr-4 py-3 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500/30 transition-shadow shadow-sm" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Daily Loss Limit (USD)</label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 font-medium">$</span>
                        <input type="number" value={maxDaily} onChange={(e) => setMaxDaily(Number(e.target.value))} min={1} step={500}
                          className="w-full text-[15px] font-medium bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl pl-8 pr-4 py-3 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500/30 transition-shadow shadow-sm" />
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 bg-indigo-50/50 dark:bg-indigo-500/10 p-4 rounded-2xl border border-indigo-100 dark:border-indigo-500/20">
                    <div className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
                    <p className="text-sm font-medium text-indigo-700 dark:text-indigo-300">System is locked to Paper Trading mode. No real capital is at risk.</p>
                  </div>
                </div>
              </div>
            </div>
          </GlassCard>

          {error && (
            <div className="px-5 py-4 rounded-2xl bg-rose-50/80 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-sm font-medium text-rose-600 dark:text-rose-400 shadow-sm animate-slide-up">
              {error}
            </div>
          )}

          <div className="pt-4">
            <Button
              type="submit"
              size="lg"
              className={cn(
                'w-full h-14 text-base font-bold transition-all duration-300 hover:-translate-y-0.5',
                mode === 'nl'
                  ? 'shadow-[0_0_20px_rgba(139,92,246,0.25)] hover:shadow-[0_0_35px_rgba(139,92,246,0.45)]'
                  : 'shadow-[0_0_20px_rgba(16,185,129,0.2)] hover:shadow-[0_0_35px_rgba(16,185,129,0.4)]',
              )}
              loading={loading}
              disabled={!ready}
            >
              {!loading && (mode === 'nl' ? <Sparkles className="w-5 h-5 mr-2" /> : <Cpu className="w-5 h-5 mr-2" />)}
              {loading
                ? (mode === 'nl' ? 'Compiling Strategy...' : 'Deploying Agent...')
                : (mode === 'nl' ? 'Deploy AI Agent' : 'Deploy Quant Agent')}
            </Button>
          </div>
        </form>
      </div>
    </AppShell>
  )
}
