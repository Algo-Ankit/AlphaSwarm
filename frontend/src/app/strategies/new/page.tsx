'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import { TIMEFRAMES, DEFAULT_SYMBOLS } from '@/lib/constants'
import { Plus, X, ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function NewStrategyPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [symbols, setSymbols] = useState<string[]>(['SPY'])
  const [timeframe, setTimeframe] = useState('1Min')
  const [showRisk, setShowRisk] = useState(false)
  const [maxOrder, setMaxOrder] = useState(1000)
  const [maxDaily, setMaxDaily] = useState(5000)
  const [symbolInput, setSymbolInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function addSymbol(sym: string) {
    const u = sym.toUpperCase().trim()
    if (u && !symbols.includes(u)) setSymbols((prev) => [...prev, u])
    setSymbolInput('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const s = await api.createStrategy({
        name, prompt, symbols, timeframe,
        risk: { max_order_notional: maxOrder, max_daily_notional: maxDaily, allowed_symbols: symbols, paper_trading_only: true },
      })
      router.push(`/strategies/${s.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const ready = name.length >= 3 && prompt.length >= 10 && symbols.length > 0

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto animate-slide-up">
        {/* Header */}
        <div className="mb-7">
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-violet-50 dark:bg-violet-500/10 text-violet-600 dark:text-violet-400 text-xs font-medium mb-3">
            <Sparkles className="w-3.5 h-3.5" />
            AI Strategy Builder
          </div>
          <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Describe your strategy</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">Plain English — the AI handles the rest.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Main prompt */}
          <GlassCard padding="none" className="overflow-hidden">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={`Tell me your strategy...\n\n"Buy SPY when the 5-min RSI drops below 30 and sell when it crosses above 70. Hard stop-loss at 2%."`}
              className="w-full min-h-[200px] p-5 text-sm leading-relaxed resize-none bg-transparent text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400/60 dark:placeholder:text-zinc-600 focus:outline-none"
              required
              minLength={10}
              maxLength={4000}
            />
            <div className="flex items-center justify-between px-5 py-3 border-t border-black/[0.05] dark:border-white/[0.05]">
              <span className="text-[11px] text-zinc-400">{prompt.length} / 4000</span>
              {prompt.length >= 10 && <Badge variant="success" dot>Ready to compile</Badge>}
            </div>
          </GlassCard>

          {/* Name + Timeframe */}
          <div className="grid grid-cols-2 gap-4">
            <GlassCard padding="sm">
              <label className="block text-[11px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-2">
                Strategy Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. SPY Momentum Bot"
                required
                minLength={3}
                maxLength={120}
                className="w-full bg-transparent text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none"
              />
            </GlassCard>

            <GlassCard padding="sm">
              <label className="block text-[11px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-2">
                Timeframe
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-transparent text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none cursor-pointer"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value} className="dark:bg-zinc-900">{tf.label}</option>
                ))}
              </select>
            </GlassCard>
          </div>

          {/* Symbols */}
          <GlassCard padding="sm">
            <label className="block text-[11px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-2.5">
              Symbols to Trade
            </label>
            <div className="flex flex-wrap gap-2 mb-3">
              {symbols.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => setSymbols((p) => p.filter((s) => s !== sym))}
                  className="inline-flex items-center gap-1 text-xs font-mono font-medium px-2.5 py-1 rounded-lg bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-400 hover:opacity-80 transition-opacity"
                >
                  {sym}<X className="w-3 h-3" />
                </button>
              ))}
              <input
                type="text"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); addSymbol(symbolInput) }
                  if (e.key === ',') { e.preventDefault(); addSymbol(symbolInput) }
                }}
                placeholder="Add symbol…"
                className="text-xs bg-transparent focus:outline-none text-zinc-700 dark:text-zinc-300 placeholder:text-zinc-400 min-w-0 w-24"
              />
            </div>
            <div className="flex gap-1.5 flex-wrap pt-3 border-t border-black/[0.05] dark:border-white/[0.05]">
              {DEFAULT_SYMBOLS.filter((s) => !symbols.includes(s)).map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => addSymbol(sym)}
                  className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 hover:text-violet-600 dark:hover:text-violet-400 transition-colors"
                >
                  + {sym}
                </button>
              ))}
            </div>
          </GlassCard>

          {/* Risk (collapsible) */}
          <GlassCard padding="none" className="overflow-hidden">
            <button
              type="button"
              onClick={() => setShowRisk(!showRisk)}
              className="w-full flex items-center justify-between px-5 py-4 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50/50 dark:hover:bg-white/[0.03] transition-colors"
            >
              <span>Risk Configuration</span>
              {showRisk ? <ChevronUp className="w-4 h-4 text-zinc-400" /> : <ChevronDown className="w-4 h-4 text-zinc-400" />}
            </button>
            {showRisk && (
              <div className={cn('px-5 pb-5 pt-2 border-t border-black/[0.05] dark:border-white/[0.05] space-y-4')}>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[11px] text-zinc-400 mb-1.5">Max Order (USD)</label>
                    <input
                      type="number"
                      value={maxOrder}
                      onChange={(e) => setMaxOrder(Number(e.target.value))}
                      min={1}
                      step={100}
                      className="w-full text-sm bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl px-3 py-2 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-400 mb-1.5">Daily Cap (USD)</label>
                    <input
                      type="number"
                      value={maxDaily}
                      onChange={(e) => setMaxDaily(Number(e.target.value))}
                      min={1}
                      step={1000}
                      className="w-full text-sm bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl px-3 py-2 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
                    />
                  </div>
                </div>
                <Badge variant="success" dot>Paper trading only — no real money at risk</Badge>
              </div>
            )}
          </GlassCard>

          {error && (
            <div className="px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/40 text-sm text-rose-700 dark:text-rose-400">
              {error}
            </div>
          )}

          <Button type="submit" size="lg" className="w-full" loading={loading} disabled={!ready}>
            {!loading && <Sparkles className="w-4 h-4" />}
            {loading ? 'Creating…' : 'Create Strategy'}
          </Button>
        </form>
      </div>
    </AppShell>
  )
}
