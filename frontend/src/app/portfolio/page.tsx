'use client'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { WealthForecastChart } from '@/components/charts/WealthForecastChart'
import { api, getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import type {
  BacktestSummary, CasHoldingInput, RiskReview, Strategy, UnifiedPortfolio, WealthForecast,
} from '@/lib/types'
import {
  Wallet, Upload, TrendingUp, Building2, Layers, Sparkles, AlertCircle, Loader2,
  ShieldAlert, ShieldCheck, Scissors, Eye, Check, Bot, FileText, CheckCircle2,
} from 'lucide-react'

/* A simulated parsed NSDL/CDSL CAS — lets a new user populate the unified view
   with one click before real broker-statement ingestion is wired up. */
const SAMPLE_CAS = {
  statement_date: '2026-06-01',
  holdings: [
    { symbol: 'RELIANCE.NS', name: 'Reliance Industries', isin: 'INE002A01018', asset_class: 'equity', broker: 'Zerodha', quantity: 40, avg_cost: 2400, current_price: 2920 },
    { symbol: 'INFY.NS', name: 'Infosys', isin: 'INE009A01021', asset_class: 'equity', broker: 'Zerodha', quantity: 60, avg_cost: 1350, current_price: 1610 },
    { symbol: 'HDFCBANK.NS', name: 'HDFC Bank', isin: 'INE040A01034', asset_class: 'equity', broker: 'Upstox', quantity: 50, avg_cost: 1500, current_price: 1685 },
    { symbol: 'NIFTYBEES', name: 'Nippon Nifty 50 ETF', isin: 'INF204KB14I2', asset_class: 'etf', broker: 'Upstox', quantity: 300, avg_cost: 220, current_price: 268 },
    { symbol: 'PARAGPARIKH', name: 'Parag Parikh Flexi Cap Fund', isin: 'INF879O01027', asset_class: 'mutual_fund', broker: 'AngelOne', quantity: 1800, avg_cost: 62, current_price: 78 },
    { symbol: 'GOLDBEES', name: 'Nippon Gold ETF', isin: 'INF204KB17I5', asset_class: 'etf', broker: 'AngelOne', quantity: 500, avg_cost: 52, current_price: 67 },
  ],
}

const CCY = '₹'
const fmt = (n: number) =>
  `${CCY}${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`

const ASSET_LABEL: Record<string, string> = {
  equity: 'Equity', etf: 'ETF', mutual_fund: 'Mutual Fund', bond: 'Bonds', other: 'Other',
}

/* Annual volatility implied by a strategy's risk-adjusted return:
   Sharpe ≈ CAGR / σ  ⇒  σ ≈ CAGR / Sharpe. Falls back to a market-like 18%
   when the backtest lacks a usable Sharpe. */
function impliedVolatility(bt: BacktestSummary | null): number {
  if (!bt || !bt.sharpe_ratio || bt.sharpe_ratio <= 0) return 0.18
  const cagr = (bt.cagr_pct ?? bt.total_return_pct) / 100
  const vol = Math.abs(cagr) / bt.sharpe_ratio
  return Math.min(0.6, Math.max(0.05, vol))
}

export default function PortfolioPage() {
  const router = useRouter()
  const { resolvedTheme } = useTheme()
  const dark = resolvedTheme === 'dark'

  const [portfolio, setPortfolio] = useState<UnifiedPortfolio | null>(null)
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Risk review state ────────────────────────────────────────
  const [risk, setRisk] = useState<RiskReview | null>(null)
  const [aiReview, setAiReview] = useState<string | null>(null)
  const [aiReviewLoading, setAiReviewLoading] = useState(false)
  const [aiReviewError, setAiReviewError] = useState<string | null>(null)

  // ── Simulator state ──────────────────────────────────────────
  const [strategyId, setStrategyId] = useState<string>('')
  const [backtest, setBacktest] = useState<BacktestSummary | null>(null)
  const [monthlySip, setMonthlySip] = useState<number>(25000)
  const [years, setYears] = useState<number>(15)
  const [forecast, setForecast] = useState<WealthForecast | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [simError, setSimError] = useState<string | null>(null)

  useEffect(() => {
    if (!getAccessToken()) { router.replace('/login'); return }
    ;(async () => {
      try {
        const [p, s] = await Promise.all([api.getUnifiedPortfolio(), api.listStrategies()])
        setPortfolio(p)
        setStrategies(s)
        if (s.length > 0) setStrategyId(s[0].id)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load portfolio')
      } finally {
        setLoading(false)
      }
    })()
  }, [router])

  // Deterministic risk scorecard — refetched whenever holdings change. Cheap and
  // key-free, so it loads eagerly; the AI narrative is fetched on demand below.
  const holdingsCount = portfolio?.holdings.length ?? 0
  useEffect(() => {
    if (holdingsCount === 0) { setRisk(null); return }
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.getRiskReview(false)
        if (!cancelled) { setRisk(r); setAiReview(null); setAiReviewError(null) }
      } catch {
        if (!cancelled) setRisk(null)
      }
    })()
    return () => { cancelled = true }
  }, [holdingsCount])

  const runAiReview = useCallback(async () => {
    setAiReviewLoading(true); setAiReviewError(null)
    try {
      const r = await api.getRiskReview(true)
      setRisk(r)
      if (r.ai_narrative) setAiReview(r.ai_narrative)
      else setAiReviewError(r.ai_error ?? 'AI review is unavailable. Add an API key in Settings → AI.')
    } catch (e) {
      setAiReviewError(e instanceof Error ? e.message : 'AI review failed')
    } finally {
      setAiReviewLoading(false)
    }
  }, [])

  // Pull the selected strategy's latest backtest so we can derive CAGR + σ.
  useEffect(() => {
    if (!strategyId) { setBacktest(null); return }
    let cancelled = false
    ;(async () => {
      try {
        const bt = await api.getLatestBacktest(strategyId)
        if (!cancelled) setBacktest(bt)
      } catch {
        if (!cancelled) setBacktest(null)  // no backtest yet → use defaults
      }
    })()
    return () => { cancelled = true }
  }, [strategyId])

  const loadSample = useCallback(async () => {
    setUploading(true); setError(null); setSuccessMsg(null)
    try {
      const res = await api.uploadCas(SAMPLE_CAS)
      setPortfolio(res)
      setSuccessMsg(`Imported ${res.holdings_count} sample holdings (${fmt(res.total_value)})`)
      setTimeout(() => setSuccessMsg(null), 5000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    setSuccessMsg(null)

    try {
      const text = await file.text()
      const isJson = file.name.endsWith('.json') || file.type.includes('json')
      let statementDate = new Date().toISOString().slice(0, 10)
      let holdings: CasHoldingInput[] = []

      if (isJson) {
        const parsed = JSON.parse(text)
        if (Array.isArray(parsed)) {
          holdings = parsed
        } else if (parsed && typeof parsed === 'object') {
          if (parsed.statement_date) statementDate = parsed.statement_date
          if (Array.isArray(parsed.holdings)) {
            holdings = parsed.holdings
          }
        }
      } else {
        // Parse CSV format (NSDL / Zerodha / Upstox / Groww / generic holdings exports)
        const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
        if (lines.length < 2) {
          throw new Error('CSV file must contain a header row and at least one data row.')
        }

        const parseCsvLine = (line: string): string[] => {
          const cells: string[] = []
          let cur = ''
          let inQuotes = false
          for (let i = 0; i < line.length; i++) {
            const ch = line[i]
            if (ch === '"' || ch === "'") {
              inQuotes = !inQuotes
            } else if (ch === ',' && !inQuotes) {
              cells.push(cur.trim())
              cur = ''
            } else {
              cur += ch
            }
          }
          cells.push(cur.trim())
          return cells
        }

        const headers = parseCsvLine(lines[0]).map(h => h.toLowerCase().replace(/[^a-z0-9]/g, ''))
        const findCol = (keywords: string[]) =>
          headers.findIndex(h => keywords.some(k => h.includes(k)))

        const colSymbol = findCol(['symbol', 'tradingsymbol', 'instrument', 'ticker', 'scrip', 'stock'])
        const colName = findCol(['name', 'company', 'desc'])
        const colIsin = findCol(['isin'])
        const colQty = findCol(['qty', 'quantity', 'units', 'shares', 'holding'])
        const colAvg = findCol(['avgcost', 'avgprice', 'buyavg', 'costprice', 'buyprice', 'avg', 'cost'])
        const colPrice = findCol(['ltp', 'curprice', 'currentprice', 'cmp', 'lastprice', 'marketprice', 'price'])
        const colBroker = findCol(['broker', 'dp', 'source', 'platform'])
        const colAsset = findCol(['assetclass', 'asset', 'type'])

        if (colSymbol === -1) {
          throw new Error('CSV header missing a symbol or instrument column (e.g. Symbol, Instrument, Ticker).')
        }
        if (colQty === -1) {
          throw new Error('CSV header missing a quantity column (e.g. Qty, Quantity, Shares).')
        }

        const cleanNum = (val: string | undefined): number => {
          if (!val) return 0
          const cleaned = val.replace(/[₹$,]/g, '').trim()
          const n = parseFloat(cleaned)
          return isNaN(n) ? 0 : n
        }

        for (let i = 1; i < lines.length; i++) {
          const cells = parseCsvLine(lines[i])
          if (cells.length <= Math.max(colSymbol, colQty)) continue

          const rawSymbol = cells[colSymbol]?.replace(/['"]/g, '').trim()
          if (!rawSymbol) continue

          const qty = cleanNum(cells[colQty])
          if (qty <= 0) continue

          const avgCost = colAvg !== -1 ? cleanNum(cells[colAvg]) : 0
          const curPrice = colPrice !== -1 ? cleanNum(cells[colPrice]) : avgCost
          const rawName = colName !== -1 ? cells[colName]?.replace(/['"]/g, '').trim() : undefined
          const isin = colIsin !== -1 ? cells[colIsin]?.replace(/['"]/g, '').trim() : undefined
          const broker = colBroker !== -1 && cells[colBroker] ? cells[colBroker].replace(/['"]/g, '').trim() : 'Broker Export'
          const assetClass = colAsset !== -1 && cells[colAsset] ? cells[colAsset].toLowerCase().replace(/['"]/g, '').trim() : 'equity'

          holdings.push({
            symbol: rawSymbol.toUpperCase(),
            name: rawName || rawSymbol,
            isin: isin || null,
            asset_class: assetClass,
            broker: broker || 'Broker Export',
            quantity: qty,
            avg_cost: avgCost,
            current_price: curPrice > 0 ? curPrice : null,
          })
        }
      }

      if (holdings.length === 0) {
        throw new Error('No valid holdings could be parsed from the uploaded file. Check that symbol and quantity columns exist.')
      }

      const res = await api.uploadCas({
        statement_date: statementDate,
        holdings,
      })
      setPortfolio(res)
      setSuccessMsg(`Successfully imported ${res.holdings_count} holdings from ${file.name}`)
      setTimeout(() => setSuccessMsg(null), 6000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import statement')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [])

  const expectedCagr = useMemo(() => {
    const c = backtest?.cagr_pct ?? backtest?.total_return_pct
    // Sensible default when no backtest exists; clamp to a believable band.
    if (c == null || !isFinite(c)) return 0.12
    return Math.min(0.5, Math.max(-0.2, c / 100))
  }, [backtest])

  const impliedVol = useMemo(() => impliedVolatility(backtest), [backtest])

  const runSimulation = useCallback(async () => {
    setSimulating(true); setSimError(null)
    try {
      const result = await api.forecastWealth({
        current_portfolio_value: portfolio?.total_value ?? 0,
        monthly_contribution: monthlySip,
        expected_cagr: expectedCagr,
        annual_volatility: impliedVol,
        years_to_forecast: years,
        simulations: 2000,
      })
      setForecast(result)
    } catch (e) {
      setSimError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setSimulating(false)
    }
  }, [portfolio, monthlySip, expectedCagr, impliedVol, years])

  const hasHoldings = (portfolio?.holdings.length ?? 0) > 0
  const finalMedian = forecast?.projections.at(-1)

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {/* ── Header ─────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-11 h-11 rounded-xl
              bg-gradient-to-br from-violet-500 to-violet-700 shadow-[0_4px_18px_rgba(124,58,237,0.45)]">
              <Wallet className="w-5.5 h-5.5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
                Unified Wealth
              </h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Every broker, one net worth — then project it forward.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.csv"
              className="hidden"
              onChange={handleFileUpload}
            />
            <Button
              variant="secondary"
              onClick={() => fileInputRef.current?.click()}
              loading={uploading}
            >
              <Upload className="w-4 h-4" /> Upload Statement (CSV / JSON)
            </Button>
            <Button
              variant="ghost"
              onClick={loadSample}
              loading={uploading}
              title="Load simulated NSDL/CDSL sample portfolio"
            >
              Sample CAS
            </Button>
          </div>
        </div>

        {successMsg && (
          <GlassCard className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/50 dark:border-emerald-800/30">
            <CheckCircle2 className="w-4 h-4 shrink-0" /> {successMsg}
          </GlassCard>
        )}

        {error && (
          <GlassCard className="flex items-center gap-2 text-sm text-rose-600 dark:text-rose-400">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </GlassCard>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-24 text-zinc-400">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : !hasHoldings ? (
          <GlassCard padding="lg" className="text-center py-16">
            <div className="mx-auto flex items-center justify-center w-14 h-14 rounded-2xl
              bg-violet-100 dark:bg-violet-500/10 mb-4">
              <Building2 className="w-7 h-7 text-violet-600 dark:text-violet-400" />
            </div>
            <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
              Consolidate your holdings
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 max-w-md mx-auto">
              Import an NSDL/CDSL statement or broker holdings export (Zerodha, Groww, Upstox, Angel One) to see every holding as a single portfolio.
            </p>
            <div className="flex items-center justify-center gap-3 mt-6">
              <Button onClick={() => fileInputRef.current?.click()} loading={uploading}>
                <Upload className="w-4 h-4" /> Upload CSV or JSON
              </Button>
              <Button variant="secondary" onClick={loadSample} loading={uploading}>
                Try Sample CAS
              </Button>
            </div>
            <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-3">
              Accepts .csv (with symbol &amp; quantity columns) or .json files.
            </p>
          </GlassCard>
        ) : (
          <>
            {/* ── Consolidated summary ─────────────────────────── */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <GlassCard>
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Net Worth</p>
                <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-50 mt-1">
                  {fmt(portfolio!.total_value)}
                </p>
                <p className="text-[11px] text-zinc-400 mt-1">
                  {portfolio!.holdings_count} holdings · {Object.keys(portfolio!.by_broker).length} brokers
                </p>
              </GlassCard>
              <GlassCard>
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Invested</p>
                <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-50 mt-1">
                  {fmt(portfolio!.total_cost)}
                </p>
                <p className="text-[11px] text-zinc-400 mt-1">Cost basis</p>
              </GlassCard>
              <GlassCard>
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Unrealized P&amp;L</p>
                <p className={cn('text-2xl font-bold mt-1',
                  portfolio!.unrealized_pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
                  {fmt(portfolio!.unrealized_pnl)}
                </p>
                <p className={cn('text-[11px] mt-1',
                  portfolio!.unrealized_pnl >= 0 ? 'text-emerald-500' : 'text-rose-500')}>
                  {fmtPct(portfolio!.unrealized_pnl_pct)}
                </p>
              </GlassCard>
            </div>

            {/* ── Breakdowns ───────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Breakdown title="By Broker" icon={Building2} data={portfolio!.by_broker}
                total={portfolio!.total_value} />
              <Breakdown title="By Asset Class" icon={Layers}
                data={Object.fromEntries(Object.entries(portfolio!.by_asset_class)
                  .map(([k, v]) => [ASSET_LABEL[k] ?? k, v]))}
                total={portfolio!.total_value} />
            </div>

            {/* ── Holdings table ───────────────────────────────── */}
            <GlassCard padding="none" className="overflow-hidden">
              <div className="px-5 py-3.5 border-b border-black/[0.06] dark:border-white/[0.06]">
                <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">Holdings</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500
                      border-b border-black/[0.06] dark:border-white/[0.06]">
                      <th className="text-left font-medium px-5 py-2.5">Instrument</th>
                      <th className="text-left font-medium px-3 py-2.5">Broker</th>
                      <th className="text-right font-medium px-3 py-2.5">Qty</th>
                      <th className="text-right font-medium px-3 py-2.5">Avg Cost</th>
                      <th className="text-right font-medium px-3 py-2.5">LTP</th>
                      <th className="text-right font-medium px-5 py-2.5">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio!.holdings.map((h, i) => {
                      const cost = h.quantity * h.avg_cost
                      const gain = h.current_value - cost
                      return (
                        <tr key={`${h.symbol}-${h.broker}-${i}`}
                          className="border-b border-black/[0.04] dark:border-white/[0.04] last:border-0
                            hover:bg-black/[0.02] dark:hover:bg-white/[0.02]">
                          <td className="px-5 py-3">
                            <div className="font-medium text-zinc-900 dark:text-zinc-100">{h.symbol}</div>
                            <div className="text-[11px] text-zinc-400 truncate max-w-[180px]">{h.name}</div>
                          </td>
                          <td className="px-3 py-3 text-zinc-500 dark:text-zinc-400">{h.broker}</td>
                          <td className="px-3 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{h.quantity}</td>
                          <td className="px-3 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">{fmt(h.avg_cost)}</td>
                          <td className="px-3 py-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300">
                            {h.current_price != null ? fmt(h.current_price) : '—'}
                          </td>
                          <td className="px-5 py-3 text-right">
                            <div className="tabular-nums font-medium text-zinc-900 dark:text-zinc-100">{fmt(h.current_value)}</div>
                            <div className={cn('text-[11px] tabular-nums',
                              gain >= 0 ? 'text-emerald-500' : 'text-rose-500')}>{fmt(gain)}</div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </GlassCard>

            {/* ── AI Risk Review ───────────────────────────────── */}
            {risk && (
              <RiskReviewCard
                risk={risk}
                aiReview={aiReview}
                aiLoading={aiReviewLoading}
                aiError={aiReviewError}
                onRunAi={runAiReview}
              />
            )}

            {/* ── Simulate Future ──────────────────────────────── */}
            <GlassCard padding="lg" glow>
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="w-5 h-5 text-violet-500" />
                <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Simulate Future</h3>
              </div>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
                Apply an AlphaSwarm strategy&apos;s return profile to your combined net worth and
                project it with a {forecast?.simulations ?? 2000}-path Monte Carlo simulation.
              </p>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
                <Field label="Strategy">
                  <select
                    value={strategyId}
                    onChange={(e) => setStrategyId(e.target.value)}
                    className="w-full h-10 px-3 rounded-xl text-sm bg-white dark:bg-zinc-900
                      border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
                      focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                  >
                    {strategies.length === 0 && <option value="">No strategies yet</option>}
                    {strategies.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-zinc-400 mt-1.5">
                    CAGR {(expectedCagr * 100).toFixed(1)}% · vol {(impliedVol * 100).toFixed(1)}%
                    {backtest ? ' (from backtest)' : ' (defaults — backtest the strategy for accuracy)'}
                  </p>
                </Field>

                <Field label="Monthly SIP">
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-zinc-400">{CCY}</span>
                    <input
                      type="number" min={0} step={1000} value={monthlySip}
                      onChange={(e) => setMonthlySip(Math.max(0, Number(e.target.value)))}
                      className="w-full h-10 pl-7 pr-3 rounded-xl text-sm tabular-nums bg-white dark:bg-zinc-900
                        border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
                        focus:outline-none focus:ring-2 focus:ring-violet-500/40"
                    />
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-1.5">Added every month on top of your net worth</p>
                </Field>

                <Field label={`Horizon — ${years} years`}>
                  <input
                    type="range" min={1} max={20} value={years}
                    onChange={(e) => setYears(Number(e.target.value))}
                    className="w-full accent-violet-600 mt-2"
                  />
                  <p className="text-[11px] text-zinc-400 mt-1.5">Project 1–20 years forward</p>
                </Field>
              </div>

              <Button onClick={runSimulation} loading={simulating}
                disabled={!portfolio || portfolio.total_value <= 0}>
                <TrendingUp className="w-4 h-4" /> Run Simulation
              </Button>

              {simError && (
                <p className="mt-3 text-sm text-rose-500 flex items-center gap-1.5">
                  <AlertCircle className="w-4 h-4" /> {simError}
                </p>
              )}

              {forecast && finalMedian && (
                <div className="mt-6">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
                    <Projection label="Pessimistic" sub="10th percentile"
                      value={finalMedian.pessimistic} color="text-rose-600 dark:text-rose-400" />
                    <Projection label="Median" sub="50th percentile"
                      value={finalMedian.median} color="text-blue-600 dark:text-blue-400" />
                    <Projection label="Optimistic" sub="90th percentile"
                      value={finalMedian.optimistic} color="text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <WealthForecastChart forecast={forecast} dark={dark} currency={CCY} />
                  <p className="text-[11px] text-zinc-400 mt-3">{forecast.disclaimer}</p>
                </div>
              )}
            </GlassCard>
          </>
        )}
      </div>
    </AppShell>
  )
}

/* ── AI Risk Review ────────────────────────────────────────────────────────── */
const SIGNAL_STYLE: Record<string, { cls: string; icon: typeof Scissors; label: string }> = {
  Trim: { cls: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20', icon: Scissors, label: 'Trim' },
  Review: { cls: 'text-rose-600 dark:text-rose-400 bg-rose-500/10 border-rose-500/20', icon: Eye, label: 'Review' },
  Hold: { cls: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20', icon: Check, label: 'Hold' },
}

const DIVERSIFICATION_STYLE: Record<string, string> = {
  diversified: 'text-emerald-600 dark:text-emerald-400',
  moderate: 'text-amber-600 dark:text-amber-400',
  concentrated: 'text-rose-600 dark:text-rose-400',
  unknown: 'text-zinc-400',
}

function SignalBadge({ signal }: { signal: string }) {
  const s = SIGNAL_STYLE[signal] ?? SIGNAL_STYLE.Hold
  const Icon = s.icon
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold border', s.cls)}>
      <Icon className="w-3 h-3" /> {s.label}
    </span>
  )
}

function RiskReviewCard({
  risk, aiReview, aiLoading, aiError, onRunAi,
}: {
  risk: RiskReview; aiReview: string | null; aiLoading: boolean
  aiError: string | null; onRunAi: () => void
}) {
  const flagged = risk.flagged_count > 0
  return (
    <GlassCard padding="lg">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <div className="flex items-center gap-2">
          {flagged
            ? <ShieldAlert className="w-5 h-5 text-amber-500" />
            : <ShieldCheck className="w-5 h-5 text-emerald-500" />}
          <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Risk Review</h3>
        </div>
        <Button variant="secondary" onClick={onRunAi} loading={aiLoading}>
          <Bot className="w-4 h-4" /> Ask AI what to sell / hold
        </Button>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">{risk.verdict}</p>

      {/* Portfolio-level risk tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        <RiskTile label="Diversification"
          value={risk.diversification[0].toUpperCase() + risk.diversification.slice(1)}
          cls={DIVERSIFICATION_STYLE[risk.diversification]} />
        <RiskTile label="Largest position" value={`${risk.top_weight_pct.toFixed(0)}%`}
          cls={risk.top_weight_pct >= 20 ? 'text-amber-600 dark:text-amber-400' : 'text-zinc-800 dark:text-zinc-200'} />
        <RiskTile label="Top broker" value={`${risk.broker_concentration_pct.toFixed(0)}%`}
          cls={risk.broker_concentration_pct >= 70 ? 'text-amber-600 dark:text-amber-400' : 'text-zinc-800 dark:text-zinc-200'} />
        <RiskTile label="Flagged" value={`${risk.flagged_count} / ${risk.holdings_count}`}
          cls={flagged ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'} />
      </div>

      {/* Per-holding signals */}
      <div className="space-y-2">
        {risk.holdings.map((h) => (
          <div key={`${h.symbol}-${h.broker}`}
            className="flex items-start justify-between gap-3 rounded-xl px-4 py-3
              bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.05] dark:border-white/[0.05]">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-zinc-900 dark:text-zinc-100">{h.symbol}</span>
                <SignalBadge signal={h.signal} />
              </div>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1">{h.reasons[0]}</p>
            </div>
            <div className="text-right flex-shrink-0 tabular-nums">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{h.weight_pct.toFixed(0)}%</p>
              {h.unrealized_pnl_pct != null && (
                <p className={cn('text-[11px]',
                  h.unrealized_pnl_pct >= 0 ? 'text-emerald-500' : 'text-rose-500')}>
                  {fmtPct(h.unrealized_pnl_pct)}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* AI narrative */}
      {aiError && (
        <p className="mt-4 text-sm text-rose-500 flex items-center gap-1.5">
          <AlertCircle className="w-4 h-4" /> {aiError}
        </p>
      )}
      {aiReview && (
        <div className="mt-5 rounded-xl px-5 py-4 bg-violet-500/[0.04] border border-violet-500/15">
          <div className="flex items-center gap-2 mb-2 text-violet-600 dark:text-violet-400">
            <Bot className="w-4 h-4" /> <span className="text-sm font-semibold">AI advisor</span>
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-headings:mt-3">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
              {aiReview}
            </ReactMarkdown>
          </div>
        </div>
      )}

      <p className="mt-4 text-[11px] text-zinc-400">
        Signals are risk heuristics on your own holdings — not personalised financial advice.
        AlphaSwarm never buys or sells on your behalf.
      </p>
    </GlassCard>
  )
}

function RiskTile({ label, value, cls }: { label: string; value: string; cls: string }) {
  return (
    <div className="rounded-xl px-3 py-2.5 bg-black/[0.02] dark:bg-white/[0.03]
      border border-black/[0.05] dark:border-white/[0.05]">
      <p className="text-[10px] uppercase tracking-wider text-zinc-400">{label}</p>
      <p className={cn('text-base font-bold mt-0.5', cls)}>{value}</p>
    </div>
  )
}

/* ── Small presentational helpers ──────────────────────────────────────────── */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">{label}</label>
      {children}
    </div>
  )
}

function Projection({ label, sub, value, color }: {
  label: string; sub: string; value: number; color: string
}) {
  return (
    <div className="rounded-xl px-4 py-3 bg-black/[0.02] dark:bg-white/[0.03]
      border border-black/[0.05] dark:border-white/[0.05]">
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={cn('text-xl font-bold mt-0.5 tabular-nums', color)}>{fmt(value)}</p>
      <p className="text-[11px] text-zinc-400 mt-0.5">{sub}</p>
    </div>
  )
}

function Breakdown({ title, icon: Icon, data, total }: {
  title: string; icon: typeof Building2; data: Record<string, number>; total: number
}) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1])
  return (
    <GlassCard>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-zinc-400" />
        <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">{title}</h3>
      </div>
      <div className="space-y-2.5">
        {rows.map(([label, value]) => {
          const pct = total > 0 ? (value / total) * 100 : 0
          return (
            <div key={label}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-zinc-600 dark:text-zinc-300">{label}</span>
                <span className="tabular-nums text-zinc-500 dark:text-zinc-400">
                  {fmt(value)} · {pct.toFixed(1)}%
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-black/[0.06] dark:bg-white/[0.06] overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-violet-600"
                  style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}
