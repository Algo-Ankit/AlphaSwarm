'use client'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api, getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { LeaderboardEntry, Strategy, SubscriptionEntry } from '@/lib/types'
import {
  Trophy, Users, TrendingUp, TrendingDown, ShieldCheck, Sparkles,
  AlertCircle, Loader2, Copy, X, BadgeCheck, Percent, CheckCircle2, Upload,
} from 'lucide-react'

const exchangeCcy = (exchange: string) =>
  exchange === 'NSE' || exchange === 'BSE' ? '₹' : '$'

const fmtPct = (n: number | null, signed = false) =>
  n == null ? '—' : `${signed && n >= 0 ? '+' : ''}${n.toFixed(1)}%`

export default function LeaderboardPage() {
  const router = useRouter()

  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [subscriptions, setSubscriptions] = useState<SubscriptionEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [copyTarget, setCopyTarget] = useState<LeaderboardEntry | null>(null)
  const [publishOpen, setPublishOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const [lb, subs] = await Promise.all([api.getLeaderboard(), api.listSubscriptions()])
      setEntries(lb)
      setSubscriptions(subs)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load leaderboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!getAccessToken()) { router.replace('/login'); return }
    load()
  }, [router, load])

  const subscribedIds = useMemo(
    () => new Set(subscriptions.map((s) => s.public_strategy_id)),
    [subscriptions],
  )

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* ── Header ─────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-11 h-11 rounded-xl
              bg-gradient-to-br from-violet-500 to-violet-700 shadow-[0_4px_18px_rgba(124,58,237,0.45)]">
              <Trophy className="w-5.5 h-5.5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
                Swarm Leaderboard
              </h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Copy the best AI strategies — they trade in your own broker account.
              </p>
            </div>
          </div>
          <Button variant="secondary" onClick={() => setPublishOpen(true)}>
            <Upload className="w-4 h-4" /> Publish a strategy
          </Button>
        </div>

        {error && (
          <GlassCard className="flex items-center gap-2 text-sm text-rose-600 dark:text-rose-400">
            <AlertCircle className="w-4 h-4" /> {error}
          </GlassCard>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-24 text-zinc-400">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <GlassCard padding="lg" className="text-center py-16">
            <div className="mx-auto flex items-center justify-center w-14 h-14 rounded-2xl
              bg-violet-100 dark:bg-violet-500/10 mb-4">
              <Sparkles className="w-7 h-7 text-violet-600 dark:text-violet-400" />
            </div>
            <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
              No published strategies yet
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 max-w-md mx-auto">
              Be the first to publish. Share a backtested strategy to the leaderboard
              and let other traders copy it.
            </p>
            <Button className="mt-5" onClick={() => setPublishOpen(true)}>
              <Upload className="w-4 h-4" /> Publish a strategy
            </Button>
          </GlassCard>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {entries.map((e, i) => (
              <StrategyCard
                key={e.public_strategy_id}
                entry={e}
                rank={i + 1}
                subscribed={subscribedIds.has(e.public_strategy_id)}
                onCopy={() => setCopyTarget(e)}
              />
            ))}
          </div>
        )}
      </div>

      {copyTarget && (
        <CopyModal
          entry={copyTarget}
          onClose={() => setCopyTarget(null)}
          onDone={() => { setCopyTarget(null); load() }}
        />
      )}
      {publishOpen && (
        <PublishModal
          onClose={() => setPublishOpen(false)}
          onDone={() => { setPublishOpen(false); load() }}
        />
      )}
    </AppShell>
  )
}

/* ── Strategy card ─────────────────────────────────────────────────────────── */
function StrategyCard({
  entry, rank, subscribed, onCopy,
}: {
  entry: LeaderboardEntry; rank: number; subscribed: boolean; onCopy: () => void
}) {
  const dd = entry.max_drawdown_pct
  return (
    <GlassCard padding="none" hover className="overflow-hidden flex flex-col">
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold text-violet-500">#{rank}</span>
              <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-50 truncate">{entry.title}</h3>
              {entry.is_verified && <BadgeCheck className="w-4 h-4 text-sky-500 flex-shrink-0" />}
            </div>
            <p className="text-[11px] text-zinc-400 mt-0.5 truncate">
              by {entry.creator_name} · {entry.symbols.slice(0, 3).join(', ')}
              {entry.symbols.length > 3 ? '…' : ''} · {entry.exchange}
            </p>
          </div>
          <span className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400 flex-shrink-0">
            <Users className="w-3.5 h-3.5" /> {entry.subscriber_count}
          </span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 divide-x divide-black/[0.06] dark:divide-white/[0.06]
        border-y border-black/[0.06] dark:border-white/[0.06]">
        <Metric label="1Y CAGR"
          value={fmtPct(entry.cagr_pct ?? entry.total_return_pct, true)}
          tone={(entry.cagr_pct ?? entry.total_return_pct ?? 0) >= 0 ? 'pos' : 'neg'}
          icon={(entry.cagr_pct ?? 0) >= 0 ? TrendingUp : TrendingDown} />
        <Metric label="Win Rate" value={fmtPct(entry.win_rate_pct)} tone="neutral" icon={Percent} />
        <Metric label="Max DD"
          value={dd == null ? '—' : `-${Math.abs(dd).toFixed(1)}%`}
          tone="neg" icon={TrendingDown} />
      </div>

      <div className="px-5 py-3 flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
        <span className="flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5" />
          Sharpe {entry.sharpe_ratio != null ? entry.sharpe_ratio.toFixed(2) : '—'}
        </span>
        <span>Fee {(entry.management_fee_bps / 100).toFixed(2)}%</span>
      </div>

      <div className="px-5 pb-4 mt-auto">
        {subscribed ? (
          <Button variant="secondary" className="w-full" disabled>
            <CheckCircle2 className="w-4 h-4" /> Copying
          </Button>
        ) : (
          <Button className="w-full" onClick={onCopy}>
            <Copy className="w-4 h-4" /> Copy Trade
          </Button>
        )}
      </div>
    </GlassCard>
  )
}

function Metric({ label, value, tone, icon: Icon }: {
  label: string; value: string; tone: 'pos' | 'neg' | 'neutral'; icon: typeof TrendingUp
}) {
  const color =
    tone === 'pos' ? 'text-emerald-600 dark:text-emerald-400'
    : tone === 'neg' ? 'text-rose-600 dark:text-rose-400'
    : 'text-zinc-800 dark:text-zinc-200'
  return (
    <div className="px-3 py-3 text-center">
      <p className="text-[10px] uppercase tracking-wider text-zinc-400 flex items-center justify-center gap-1">
        <Icon className="w-3 h-3" /> {label}
      </p>
      <p className={cn('text-base font-bold tabular-nums mt-0.5', color)}>{value}</p>
    </div>
  )
}

/* ── Copy Trade modal ──────────────────────────────────────────────────────── */
function CopyModal({
  entry, onClose, onDone,
}: {
  entry: LeaderboardEntry; onClose: () => void; onDone: () => void
}) {
  const ccy = exchangeCcy(entry.exchange)
  const [amount, setAmount] = useState<number>(50000)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.subscribeStrategy(entry.public_strategy_id, amount)
      onDone()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not copy this strategy')
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="flex items-center gap-2 mb-1">
        <Copy className="w-5 h-5 text-violet-500" />
        <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Copy “{entry.title}”</h3>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
        Dedicate buying power to this strategy. Its signals will be mirrored into your own
        broker account, sized proportionally to the capital you allocate.
      </p>

      <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">
        Capital to allocate
      </label>
      <div className="relative mb-2">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-zinc-400">{ccy}</span>
        <input
          type="number" min={0} step={1000} value={amount} autoFocus
          onChange={(e) => setAmount(Math.max(0, Number(e.target.value)))}
          className="w-full h-11 pl-7 pr-3 rounded-xl text-sm tabular-nums bg-white dark:bg-zinc-900
            border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
            focus:outline-none focus:ring-2 focus:ring-violet-500/40"
        />
      </div>
      <div className="flex gap-2 mb-5">
        {[25000, 50000, 100000, 250000].map((v) => (
          <button key={v} onClick={() => setAmount(v)}
            className={cn('flex-1 h-8 rounded-lg text-xs font-medium transition-colors',
              amount === v
                ? 'bg-violet-600 text-white'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700')}>
            {ccy}{(v / 1000)}k
          </button>
        ))}
      </div>

      <div className="rounded-xl px-4 py-3 mb-5 bg-black/[0.02] dark:bg-white/[0.03]
        border border-black/[0.05] dark:border-white/[0.05] text-[11px] text-zinc-500 dark:text-zinc-400">
        Management fee {(entry.management_fee_bps / 100).toFixed(2)}% · the platform never holds your
        funds — trades execute in your connected broker account.
      </div>

      {err && (
        <p className="mb-3 text-sm text-rose-500 flex items-center gap-1.5">
          <AlertCircle className="w-4 h-4" /> {err}
        </p>
      )}

      <div className="flex gap-2">
        <Button variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button className="flex-1" onClick={submit} loading={busy} disabled={amount <= 0}>
          Confirm Copy
        </Button>
      </div>
    </Modal>
  )
}

/* ── Publish modal ─────────────────────────────────────────────────────────── */
function PublishModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyId, setStrategyId] = useState('')
  const [title, setTitle] = useState('')
  const [feePct, setFeePct] = useState(1)
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.listStrategies()
      .then((s) => {
        setStrategies(s)
        if (s.length > 0) { setStrategyId(s[0].id); setTitle(s[0].name) }
      })
      .catch(() => setErr('Could not load your strategies'))
  }, [])

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      await api.publishStrategy({
        strategy_id: strategyId,
        title: title.trim(),
        description: description.trim(),
        management_fee_bps: Math.round(feePct * 100),
      })
      onDone()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not publish')
      setBusy(false)
    }
  }

  return (
    <Modal onClose={onClose}>
      <div className="flex items-center gap-2 mb-1">
        <Upload className="w-5 h-5 text-violet-500" />
        <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Publish to leaderboard</h3>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
        Share one of your strategies. Others can copy it and its signals fan out to their
        accounts in real time.
      </p>

      {strategies.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
          You have no strategies yet. Create one first.
        </p>
      ) : (
        <div className="space-y-4 mb-5">
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">Strategy</label>
            <select value={strategyId}
              onChange={(e) => {
                setStrategyId(e.target.value)
                const s = strategies.find((x) => x.id === e.target.value)
                if (s) setTitle(s.name)
              }}
              className="w-full h-10 px-3 rounded-xl text-sm bg-white dark:bg-zinc-900
                border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
                focus:outline-none focus:ring-2 focus:ring-violet-500/40">
              {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">Public title</label>
            <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)}
              className="w-full h-10 px-3 rounded-xl text-sm bg-white dark:bg-zinc-900
                border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
                focus:outline-none focus:ring-2 focus:ring-violet-500/40" />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">
              Management fee — {feePct.toFixed(2)}%
            </label>
            <input type="range" min={0} max={20} step={0.25} value={feePct}
              onChange={(e) => setFeePct(Number(e.target.value))}
              className="w-full accent-violet-600" />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1.5">
              Description <span className="text-zinc-400">(optional)</span>
            </label>
            <textarea value={description} rows={2} maxLength={2000}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-zinc-900
                border border-black/10 dark:border-white/10 text-zinc-800 dark:text-zinc-200
                focus:outline-none focus:ring-2 focus:ring-violet-500/40 resize-none" />
          </div>
        </div>
      )}

      {err && (
        <p className="mb-3 text-sm text-rose-500 flex items-center gap-1.5">
          <AlertCircle className="w-4 h-4" /> {err}
        </p>
      )}

      <div className="flex gap-2">
        <Button variant="secondary" className="flex-1" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button className="flex-1" onClick={submit} loading={busy}
          disabled={strategies.length === 0 || !strategyId || title.trim().length < 3}>
          Publish
        </Button>
      </div>
    </Modal>
  )
}

/* ── Modal shell ───────────────────────────────────────────────────────────── */
function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md">
        <GlassCard padding="lg" glow className="relative">
          <button onClick={onClose}
            className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors">
            <X className="w-4 h-4" />
          </button>
          {children}
        </GlassCard>
      </div>
    </div>
  )
}
