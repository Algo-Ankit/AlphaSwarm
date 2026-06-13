'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import { Search, Wifi, WifiOff, TrendingUp, Newspaper, LineChart, ExternalLink, BarChart3, Sparkles } from 'lucide-react'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Badge } from '@/components/ui/Badge'
import { CandleChart } from '@/components/charts/CandleChart'
import { RsiPane } from '@/components/charts/RsiPane'
import { api, getAccessToken, barsSocketUrl } from '@/lib/api'
import { openReconnectingSocket, type WsStatus } from '@/lib/ws'
import { sessionStatus, SESSION_LABEL, SESSION_VARIANT } from '@/lib/marketHours'
import { TIMEFRAMES } from '@/lib/constants'
import { ema, rsi } from '@/lib/ta'
import { cn } from '@/lib/utils'
import type {
  Bar, BarTick, Forecast, IndicatorSnapshot, NewsItem, TickerSearchResult,
} from '@/lib/types'

const INR = new Set(['NSE', 'BSE'])
function fmtPrice(n: number, exchange: string): string {
  const symbol = INR.has(exchange.toUpperCase()) ? '₹' : '$'
  return symbol + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

type Tab = 'forecast' | 'news' | 'performance' | 'ai'

export default function TerminalPage() {
  const router = useRouter()
  const { resolvedTheme } = useTheme()
  const dark = resolvedTheme === 'dark'

  const [symbol, setSymbol] = useState('AAPL')
  const [exchange, setExchange] = useState('NASDAQ')
  const [timeframe, setTimeframe] = useState('1d')

  const [bars, setBars] = useState<Bar[]>([])
  const [liveBar, setLiveBar] = useState<Bar | null>(null)
  const [indicators, setIndicators] = useState<IndicatorSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsStatus, setWsStatus] = useState<WsStatus>('closed')

  const [tab, setTab] = useState<Tab>('forecast')

  // ── Auth guard ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!getAccessToken()) router.replace('/login')
  }, [router])

  // ── Load history + indicator snapshot on symbol/tf/exchange change ───────
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setLiveBar(null)
    Promise.all([
      api.getBars(symbol, { exchange, timeframe, limit: 400 }),
      api.getIndicators(symbol, { exchange, timeframe }).catch(() => null),
    ])
      .then(([b, ind]) => {
        if (cancelled) return
        setBars(b)
        setIndicators(ind)
        if (b.length === 0) setError(`No market data for ${symbol} on ${exchange}.`)
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, exchange, timeframe])

  // ── Live bars WebSocket (auto-reconnecting) ─────────────────────────────
  useEffect(() => {
    if (!getAccessToken()) return
    const sock = openReconnectingSocket<BarTick>(
      () => barsSocketUrl(symbol, exchange, timeframe),
      {
        onMessage: (msg) => { if (msg.type === 'bar') setLiveBar(msg) },
        onStatus: setWsStatus,
      },
    )
    return () => sock.close()
  }, [symbol, exchange, timeframe])

  const session = sessionStatus(exchange)
  const lastClose = liveBar?.close ?? bars[bars.length - 1]?.close ?? null
  const prevClose = bars.length >= 2 ? bars[bars.length - 2].close : null
  const changePct = lastClose != null && prevClose ? ((lastClose - prevClose) / prevClose) * 100 : null

  const pickSymbol = (r: TickerSearchResult) => {
    setSymbol(r.symbol.toUpperCase())
    setExchange(r.exchange.toUpperCase())
  }

  return (
    <AppShell>
      <div className="space-y-5" style={{ animation: 'fadeIn 0.2s ease-out' }}>
        {/* ── Header: search + symbol + price + session ─────────────────── */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-4 justify-between">
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-3xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight">{symbol}</h1>
                <Badge variant="default">{exchange}</Badge>
              </div>
              <div className="flex items-center gap-3 mt-1.5">
                {lastClose != null && (
                  <span className="text-lg font-bold text-zinc-800 dark:text-zinc-100 tabular-nums">
                    {fmtPrice(lastClose, exchange)}
                  </span>
                )}
                {changePct != null && (
                  <span className={cn('text-sm font-semibold tabular-nums',
                    changePct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
                    {changePct >= 0 ? '▲' : '▼'} {Math.abs(changePct).toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            <SymbolSearch onPick={pickSymbol} />
            <Badge variant={SESSION_VARIANT[session]} dot pulse={session === 'open'}>
              {SESSION_LABEL[session]}
            </Badge>
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 dark:text-zinc-500"
              title={`Live feed: ${wsStatus}`}>
              {wsStatus === 'open'
                ? <Wifi className="w-4 h-4 text-emerald-500" />
                : <WifiOff className="w-4 h-4 text-zinc-400" />}
              {wsStatus === 'open' ? 'Live' : wsStatus === 'connecting' ? 'Connecting' : 'Offline'}
            </span>
          </div>
        </div>

        {/* ── Timeframe selector ───────────────────────────────────────── */}
        <div className="flex items-center gap-1 p-1 rounded-xl bg-zinc-100/70 dark:bg-zinc-800/50 w-fit">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={cn(
                'px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-150',
                timeframe === tf.value
                  ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300',
              )}
            >
              {tf.label}
            </button>
          ))}
        </div>

        {/* ── Chart ─────────────────────────────────────────────────────── */}
        <GlassCard padding="sm">
          {loading ? (
            <div className="h-[420px] animate-pulse rounded-xl bg-zinc-100/60 dark:bg-white/[0.03]" />
          ) : error ? (
            <div className="h-[420px] flex items-center justify-center text-sm text-rose-500 dark:text-rose-400">{error}</div>
          ) : (
            <>
              <CandleChart bars={bars} liveBar={liveBar} dark={dark} />
              <div className="mt-3 flex items-center gap-4 px-1 text-[11px] font-medium">
                <span className="text-blue-500">— EMA 20</span>
                <span className="text-amber-500">— EMA 50</span>
              </div>
            </>
          )}
        </GlassCard>

        {/* ── Indicator readout + RSI pane ──────────────────────────────── */}
        {!loading && !error && bars.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <GlassCard padding="md" className="lg:col-span-2">
              <RsiPane bars={bars} dark={dark} />
            </GlassCard>
            <GlassCard padding="md">
              <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-3">
                Indicators (latest)
              </p>
              {indicators ? (
                <div className="space-y-2">
                  {Object.entries(indicators.indicators).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between text-sm">
                      <span className="text-zinc-500 dark:text-zinc-400 font-mono">{k}</span>
                      <span className="font-semibold text-zinc-800 dark:text-zinc-200 tabular-nums">
                        {v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-400 dark:text-zinc-500">Unavailable.</p>
              )}
            </GlassCard>
          </div>
        )}

        {/* ── Intelligence tabs ─────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-1 mb-4 flex-wrap">
            <TabButton active={tab === 'forecast'} onClick={() => setTab('forecast')} icon={LineChart}>Forecast</TabButton>
            <TabButton active={tab === 'news'} onClick={() => setTab('news')} icon={Newspaper}>News & Sentiment</TabButton>
            <TabButton active={tab === 'performance'} onClick={() => setTab('performance')} icon={BarChart3}>Performance</TabButton>
            <TabButton active={tab === 'ai'} onClick={() => setTab('ai')} icon={Sparkles}>AI Analysis</TabButton>
          </div>
          {tab === 'forecast' && <ForecastTab symbol={symbol} exchange={exchange} />}
          {tab === 'news' && <NewsTab symbol={symbol} exchange={exchange} />}
          {tab === 'performance' && <PerformanceTab bars={bars} exchange={exchange} timeframe={timeframe} />}
          {tab === 'ai' && <AiAnalysisTab symbol={symbol} exchange={exchange} bars={bars} />}
        </div>
      </div>
    </AppShell>
  )
}

/* ── Symbol search ─────────────────────────────────────────────────────── */
function SymbolSearch({ onPick }: { onPick: (r: TickerSearchResult) => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<TickerSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (q.trim().length === 0) { setResults([]); return }
    const id = setTimeout(() => {
      api.searchTickers(q.trim(), 8).then(setResults).catch(() => setResults([]))
    }, 200)
    return () => clearTimeout(id)
  }, [q])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div ref={boxRef} className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="Search ticker…"
          className="w-48 h-9 pl-9 pr-3 rounded-xl text-sm bg-white dark:bg-zinc-800/80
            border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100
            placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
        />
      </div>
      {open && results.length > 0 && (
        <div className="absolute right-0 mt-2 w-72 z-50 rounded-xl overflow-hidden
          bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 shadow-xl">
          {results.map((r) => (
            <button
              key={`${r.symbol}-${r.exchange}`}
              onClick={() => { onPick(r); setQ(''); setOpen(false); setResults([]) }}
              className="w-full flex items-center justify-between px-4 py-2.5 text-left
                hover:bg-zinc-50 dark:hover:bg-white/[0.04] transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{r.symbol}</p>
                <p className="text-xs text-zinc-400 dark:text-zinc-500 truncate">{r.name}</p>
              </div>
              <Badge variant="muted">{r.exchange}</Badge>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Tab button ────────────────────────────────────────────────────────── */
function TabButton({ active, onClick, icon: Icon, children }: {
  active: boolean; onClick: () => void; icon: typeof TrendingUp; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-150',
        active
          ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'
          : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300',
      )}
    >
      <Icon className="w-4 h-4" />
      {children}
    </button>
  )
}

/* ── Forecast tab ──────────────────────────────────────────────────────── */
function ForecastTab({ symbol, exchange }: { symbol: string; exchange: string }) {
  const [data, setData] = useState<Forecast | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setData(null)
    api.getForecast(symbol, { exchange, horizon: 7 })
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e: Error) => { if (!cancelled) setError(parseErr(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, exchange])

  if (loading) return <GlassCard padding="lg"><Loading /></GlassCard>
  if (error) return <GlassCard padding="lg"><p className="text-sm text-zinc-400 dark:text-zinc-500">{error}</p></GlassCard>
  if (!data) return null

  return (
    <GlassCard padding="lg">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
          {data.horizon_days}-day forecast · <span className="font-mono">{data.model}</span>
        </p>
        {data.mape != null && (
          <Badge variant="info">MAPE {data.mape.toFixed(1)}%</Badge>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              <th className="py-2 font-semibold">Date</th>
              <th className="py-2 font-semibold text-right">Forecast</th>
              <th className="py-2 font-semibold text-right">Low</th>
              <th className="py-2 font-semibold text-right">High</th>
            </tr>
          </thead>
          <tbody>
            {data.forecast.map((p) => (
              <tr key={p.date} className="border-t border-zinc-100 dark:border-white/[0.05]">
                <td className="py-2 text-zinc-600 dark:text-zinc-400">{p.date}</td>
                <td className="py-2 text-right font-semibold text-zinc-800 dark:text-zinc-200 tabular-nums">{fmtPrice(p.yhat, exchange)}</td>
                <td className="py-2 text-right text-zinc-500 tabular-nums">{fmtPrice(p.yhat_lower, exchange)}</td>
                <td className="py-2 text-right text-zinc-500 tabular-nums">{fmtPrice(p.yhat_upper, exchange)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-4 italic">{data.disclaimer}</p>
    </GlassCard>
  )
}

/* ── News tab ──────────────────────────────────────────────────────────── */
const SENTIMENT_VARIANT = { positive: 'success', negative: 'danger', neutral: 'muted' } as const

function NewsTab({ symbol, exchange }: { symbol: string; exchange: string }) {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null); setItems([])
    api.getNews(symbol, { exchange, days: 7, limit: 20 })
      .then((d) => { if (!cancelled) setItems(d) })
      .catch((e: Error) => { if (!cancelled) setError(parseErr(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, exchange])

  if (loading) return <GlassCard padding="lg"><Loading /></GlassCard>
  if (error) return <GlassCard padding="lg"><p className="text-sm text-zinc-400 dark:text-zinc-500">{error}</p></GlassCard>
  if (items.length === 0) return <GlassCard padding="lg"><p className="text-sm text-zinc-400 dark:text-zinc-500">No recent news.</p></GlassCard>

  return (
    <div className="space-y-3">
      {items.map((n, i) => (
        <GlassCard key={`${n.url}-${i}`} padding="md" hover>
          <a href={n.url} target="_blank" rel="noopener noreferrer" className="block group">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 group-hover:text-violet-600 dark:group-hover:text-violet-400 transition-colors">
                {n.headline}
              </p>
              <Badge variant={SENTIMENT_VARIANT[n.sentiment] ?? 'muted'}>{n.sentiment}</Badge>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1.5 line-clamp-2">{n.summary}</p>
            <div className="flex items-center gap-2 mt-2.5 text-[11px] text-zinc-400 dark:text-zinc-500">
              <span className="font-medium">{n.source}</span>
              <span>·</span>
              <span>{new Date(n.published_at).toLocaleDateString()}</span>
              <ExternalLink className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </a>
        </GlassCard>
      ))}
    </div>
  )
}

/* ── Performance tab (computed client-side from loaded bars) ───────────── */
function PerformanceTab({ bars, exchange, timeframe }: { bars: Bar[]; exchange: string; timeframe: string }) {
  if (bars.length < 2) {
    return <GlassCard padding="lg"><p className="text-sm text-zinc-400 dark:text-zinc-500">Not enough data.</p></GlassCard>
  }
  const closes = bars.map((b) => b.close)
  const first = closes[0]
  const last = closes[closes.length - 1]
  const windowReturn = ((last - first) / first) * 100

  // Per-bar simple returns → stdev → annualized (periods/year per timeframe).
  const rets: number[] = []
  for (let i = 1; i < closes.length; i++) rets.push((closes[i] - closes[i - 1]) / closes[i - 1])
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length
  const periodsPerYear: Record<string, number> = { '1m': 98280, '5m': 19656, '15m': 6552, '1h': 1638, '4h': 1638, '1d': 252, '1w': 52 }
  const annVol = Math.sqrt(variance) * Math.sqrt(periodsPerYear[timeframe] ?? 252) * 100

  const highs = bars.map((b) => b.high)
  const lows = bars.map((b) => b.low)
  const periodHigh = Math.max(...highs)
  const periodLow = Math.min(...lows)
  const avgVol = bars.reduce((a, b) => a + b.volume, 0) / bars.length
  const e20 = ema(closes, 20)
  const lastE20 = e20[e20.length - 1]
  const vsEma = Number.isNaN(lastE20) ? null : ((last - lastE20) / lastE20) * 100

  const fmt = (n: number) => fmtPrice(n, exchange)
  const items: { label: string; value: string; tone?: 'up' | 'down' }[] = [
    { label: `Return (${bars.length} bars)`, value: `${windowReturn >= 0 ? '+' : ''}${windowReturn.toFixed(2)}%`, tone: windowReturn >= 0 ? 'up' : 'down' },
    { label: 'Annualized volatility', value: `${annVol.toFixed(1)}%` },
    { label: 'Period high', value: fmt(periodHigh) },
    { label: 'Period low', value: fmt(periodLow) },
    { label: 'Avg volume', value: Math.round(avgVol).toLocaleString('en-US') },
    ...(vsEma != null ? [{ label: 'Price vs EMA-20', value: `${vsEma >= 0 ? '+' : ''}${vsEma.toFixed(2)}%`, tone: (vsEma >= 0 ? 'up' : 'down') as 'up' | 'down' }] : []),
  ]

  return (
    <GlassCard padding="lg">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
        {items.map((it) => (
          <div key={it.label}>
            <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">{it.label}</p>
            <p className={cn('text-xl font-bold mt-1 tabular-nums',
              it.tone === 'up' ? 'text-emerald-600 dark:text-emerald-400'
              : it.tone === 'down' ? 'text-rose-600 dark:text-rose-400'
              : 'text-zinc-800 dark:text-zinc-200')}>
              {it.value}
            </p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-5 italic">
        Computed from the {bars.length} loaded {timeframe} bars — descriptive statistics, not a return guarantee.
      </p>
    </GlassCard>
  )
}

/* ── AI Analysis tab (signal synthesis: trend + momentum + forecast + news) ── */
type Bias = 'Bullish' | 'Neutral' | 'Bearish'

function AiAnalysisTab({ symbol, exchange, bars }: { symbol: string; exchange: string; bars: Bar[] }) {
  const [forecast, setForecast] = useState<Forecast | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setForecast(null); setNews([])
    Promise.all([
      api.getForecast(symbol, { exchange, horizon: 5 }).catch(() => null),
      api.getNews(symbol, { exchange, days: 7, limit: 20 }).catch(() => []),
    ]).then(([f, n]) => { if (!cancelled) { setForecast(f); setNews(n) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, exchange])

  if (loading) return <GlassCard padding="lg"><Loading /></GlassCard>
  if (bars.length < 50) {
    return <GlassCard padding="lg"><p className="text-sm text-zinc-400 dark:text-zinc-500">Not enough history for analysis.</p></GlassCard>
  }

  const closes = bars.map((b) => b.close)
  const last = closes[closes.length - 1]
  const e20 = ema(closes, 20); const e50 = ema(closes, 50)
  const lastE20 = e20[e20.length - 1]; const lastE50 = e50[e50.length - 1]
  const r = rsi(closes, 14); const lastRsi = r[r.length - 1]

  // Score each signal in [-1, 1], then average → overall bias.
  const signals: { label: string; verdict: string; score: number }[] = []

  // Trend
  let trendScore = 0
  let trendVerdict = 'Sideways — EMAs entwined'
  if (!Number.isNaN(lastE20) && !Number.isNaN(lastE50)) {
    if (lastE20 > lastE50 && last > lastE50) { trendScore = 1; trendVerdict = 'Uptrend — price above rising EMA stack' }
    else if (lastE20 < lastE50 && last < lastE50) { trendScore = -1; trendVerdict = 'Downtrend — price below falling EMA stack' }
  }
  signals.push({ label: 'Trend (EMA 20/50)', verdict: trendVerdict, score: trendScore })

  // Momentum
  let momScore = 0
  let momVerdict = `RSI ${lastRsi.toFixed(0)} — neutral`
  if (!Number.isNaN(lastRsi)) {
    if (lastRsi >= 70) { momScore = -0.5; momVerdict = `RSI ${lastRsi.toFixed(0)} — overbought, pullback risk` }
    else if (lastRsi <= 30) { momScore = 0.5; momVerdict = `RSI ${lastRsi.toFixed(0)} — oversold, bounce potential` }
    else if (lastRsi > 55) { momScore = 0.4; momVerdict = `RSI ${lastRsi.toFixed(0)} — positive momentum` }
    else if (lastRsi < 45) { momScore = -0.4; momVerdict = `RSI ${lastRsi.toFixed(0)} — fading momentum` }
  }
  signals.push({ label: 'Momentum (RSI 14)', verdict: momVerdict, score: momScore })

  // Forecast direction
  if (forecast && forecast.forecast.length > 0) {
    const target = forecast.forecast[forecast.forecast.length - 1].yhat
    const chg = ((target - last) / last) * 100
    const fScore = Math.max(-1, Math.min(1, chg / 5))
    signals.push({
      label: `Forecast (${forecast.model})`,
      verdict: `${chg >= 0 ? '+' : ''}${chg.toFixed(1)}% projected over ${forecast.horizon_days}d → ${fmtPrice(target, exchange)}`,
      score: fScore,
    })
  }

  // News sentiment balance
  if (news.length > 0) {
    const pos = news.filter((n) => n.sentiment === 'positive').length
    const neg = news.filter((n) => n.sentiment === 'negative').length
    const nScore = (pos - neg) / news.length
    signals.push({
      label: 'News sentiment',
      verdict: `${pos} positive / ${neg} negative across ${news.length} stories`,
      score: nScore,
    })
  }

  const overall = signals.reduce((a, s) => a + s.score, 0) / signals.length
  const bias: Bias = overall > 0.25 ? 'Bullish' : overall < -0.25 ? 'Bearish' : 'Neutral'
  const biasVariant = bias === 'Bullish' ? 'success' : bias === 'Bearish' ? 'danger' : 'muted'

  return (
    <GlassCard padding="lg" glow>
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-5 h-5 text-violet-500" />
          <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100">{symbol} signal synthesis</h3>
        </div>
        <Badge variant={biasVariant} dot>{bias}</Badge>
      </div>

      <div className="space-y-3">
        {signals.map((s) => (
          <div key={s.label} className="flex items-start gap-3">
            <span className={cn('mt-1.5 w-2 h-2 rounded-full flex-shrink-0',
              s.score > 0.15 ? 'bg-emerald-500' : s.score < -0.15 ? 'bg-rose-500' : 'bg-zinc-400')} />
            <div>
              <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{s.label}</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{s.verdict}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-5 italic">
        Rule-based synthesis of technicals, the price forecast, and news sentiment — for research only, not investment advice.
      </p>
    </GlassCard>
  )
}

/* ── Shared bits ───────────────────────────────────────────────────────── */
function Loading() {
  return <div className="h-24 flex items-center justify-center">
    <span className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
  </div>
}

function parseErr(e: Error): string {
  try { return (JSON.parse(e.message).detail as string) ?? e.message } catch { return e.message }
}
