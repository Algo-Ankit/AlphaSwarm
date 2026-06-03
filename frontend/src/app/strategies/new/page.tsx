'use client'
import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import { TIMEFRAMES, DEFAULT_SYMBOLS } from '@/lib/constants'
import { X, ChevronDown, ChevronUp, Sparkles, Activity, ShieldAlert, Cpu } from 'lucide-react'
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
  const symbolInputRef = useRef<HTMLInputElement>(null)

  function addSymbol(sym: string) {
    const u = sym.toUpperCase().trim()
    if (u && !symbols.includes(u)) setSymbols((prev) => [...prev, u])
    setSymbolInput('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    
    // Auto-add any pending symbol text before submitting
    let finalSymbols = [...symbols]
    const pendingSymbol = symbolInput.toUpperCase().trim()
    if (pendingSymbol && !symbols.includes(pendingSymbol)) {
      finalSymbols.push(pendingSymbol)
      setSymbols(finalSymbols)
      setSymbolInput('')
    }

    if (finalSymbols.length === 0) {
      setError('Please add at least one symbol to trade.')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const s = await api.createStrategy({
        name, prompt, symbols: finalSymbols, timeframe,
        risk: { max_order_notional: maxOrder, max_daily_notional: maxDaily, allowed_symbols: finalSymbols, paper_trading_only: true },
      })
      router.push(`/strategies/${s.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setLoading(false)
    }
  }

  const ready = name.length >= 3 && prompt.length >= 10 && (symbols.length > 0 || symbolInput.trim().length > 0)

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto animate-slide-up relative z-10 pb-20">
        {/* Header */}
        <div className="mb-10 flex flex-col items-center text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 border border-violet-500/20 text-violet-500 dark:text-violet-300 text-xs font-bold uppercase tracking-widest mb-4 shadow-[0_0_20px_rgba(139,92,246,0.15)]">
            <Cpu className="w-4 h-4" />
            AI Strategy Generator
          </div>
          <h2 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-600 dark:from-white dark:to-zinc-400 tracking-tight mb-3">Design Your Alpha</h2>
          <p className="text-base text-zinc-500 dark:text-zinc-400 max-w-lg leading-relaxed">
            Describe your trading logic in plain English. Our AI will compile it into a high-performance, live-execution bot.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Main prompt */}
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
                required
                minLength={10}
                maxLength={4000}
              />
            </div>
            <div className="flex items-center justify-between px-6 py-4 bg-zinc-50/50 dark:bg-zinc-900/50 border-t border-black/[0.05] dark:border-white/[0.05]">
              <span className="text-xs font-medium text-zinc-400">{prompt.length} / 4000</span>
              {prompt.length >= 10 && <Badge variant="success" dot className="animate-fade-in shadow-sm">Ready to compile</Badge>}
            </div>
          </GlassCard>

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
                    e.preventDefault(); 
                    if (symbolInput.trim()) addSymbol(symbolInput);
                  }
                }}
                onBlur={() => {
                  if (symbolInput.trim()) addSymbol(symbolInput);
                }}
                placeholder="Type ticker & press Enter…"
                className="text-sm font-medium bg-transparent focus:outline-none text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400/70 min-w-0 flex-1 ml-1"
              />
            </div>
            <div className="flex gap-2 flex-wrap pt-4 border-t border-black/[0.05] dark:border-white/[0.05]">
              {DEFAULT_SYMBOLS.filter((s) => !symbols.includes(s)).map((sym) => (
                <button
                  key={sym}
                  type="button"
                  onClick={() => { addSymbol(sym); symbolInputRef.current?.focus(); }}
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
              "grid transition-all duration-300 ease-in-out",
              showRisk ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
            )}>
              <div className="overflow-hidden">
                <div className="px-6 pb-6 pt-2 border-t border-black/[0.05] dark:border-white/[0.05] space-y-6">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Max Position (USD)</label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 font-medium">$</span>
                        <input
                          type="number"
                          value={maxOrder}
                          onChange={(e) => setMaxOrder(Number(e.target.value))}
                          min={1}
                          step={100}
                          className="w-full text-[15px] font-medium bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl pl-8 pr-4 py-3 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500/30 transition-shadow shadow-sm"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Daily Loss Limit (USD)</label>
                      <div className="relative">
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 font-medium">$</span>
                        <input
                          type="number"
                          value={maxDaily}
                          onChange={(e) => setMaxDaily(Number(e.target.value))}
                          min={1}
                          step={500}
                          className="w-full text-[15px] font-medium bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-2xl pl-8 pr-4 py-3 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500/30 transition-shadow shadow-sm"
                        />
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
            <Button type="submit" size="lg" className="w-full h-14 text-base font-bold shadow-[0_0_20px_rgba(139,92,246,0.25)] hover:shadow-[0_0_35px_rgba(139,92,246,0.45)] hover:-translate-y-0.5 transition-all duration-300" loading={loading} disabled={!ready}>
              {!loading && <Sparkles className="w-5 h-5 mr-2" />}
              {loading ? 'Compiling Strategy...' : 'Deploy AI Agent'}
            </Button>
          </div>
        </form>
      </div>
    </AppShell>
  )
}
