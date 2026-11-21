'use client'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api, getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { LeaderboardEntry, LineageResponse, Strategy, SubscriptionEntry } from '@/lib/types'
import {
  Trophy, Users, TrendingUp, TrendingDown, ShieldCheck, Sparkles,
  AlertCircle, Loader2, Copy, X, BadgeCheck, Percent, CheckCircle2, Upload,
  GitFork, GitBranch, Network, FlaskConical,
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
  const [lineageTarget, setLineageTarget] = useState<LeaderboardEntry | null>(null)
  const [publishOpen, setPublishOpen] = useState(false)
  const [forkingId, setForkingId] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)

  const forkStrategy = useCallback(async (entry: LeaderboardEntry) => {
    setForkingId(entry.public_strategy_id)
    setError(null)
    try {
      const res = await api.forkStrategy(entry.public_strategy_id)
      setBanner(`Forked into “${res.name}” — edit and backtest it in your workspace.`)
      router.push(`/strategies/${res.strategy_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not fork this strategy')
    } finally {
      setForkingId(null)
    }
  }, [router])

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

  const [unsubscribingId, setUnsubscribingId] = useState<string | null>(null)

  async function handleUnsubscribe(publicStrategyId: string) {
    if (!confirm('Stop copying this strategy? Your existing open positions will remain in your broker.')) return
    setUnsubscribingId(publicStrategyId)
    try {
      await api.unsubscribeStrategy(publicStrategyId)
      await load()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to unsubscribe')
    } finally {
      setUnsubscribingId(null)
    }
  }

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
        {banner && (
          <GlassCard className="flex items-center justify-between gap-2 text-sm text-emerald-600 dark:text-emerald-400">
            <span className="flex items-center gap-2"><GitFork className="w-4 h-4" /> {banner}</span>
            <button onClick={() => setBanner(null)} className="text-zinc-400 hover:text-zinc-600">
              <X className="w-4 h-4" />
            </button>
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
                forking={forkingId === e.public_strategy_id}
                unsubscribing={unsubscribingId === e.public_strategy_id}
                onCopy={() => setCopyTarget(e)}
                onFork={() => forkStrategy(e)}
                onLineage={() => setLineageTarget(e)}
                onUnsubscribe={() => handleUnsubscribe(e.public_strategy_id)}
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
      {lineageTarget && (
        <LineageModal entry={lineageTarget} onClose={() => setLineageTarget(null)} />
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
  entry, rank, subscribed, forking, unsubscribing, onCopy, onFork, onLineage, onUnsubscribe,
}: {
  entry: LeaderboardEntry; rank: number; subscribed: boolean; forking: boolean; unsubscribing?: boolean
  onCopy: () => void; onFork: () => void; onLineage: () => void; onUnsubscribe: () => void
}) {
  const dd = entry.max_drawdown_pct
  const hasLineage = entry.fork_count > 0 || entry.forked_from_public_strategy_id != null
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
            {entry.forked_from_public_strategy_id && (
              <p className="text-[10px] text-violet-500 mt-1 flex items-center gap-1">
                <GitBranch className="w-3 h-3" /> forked from another strategy
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <span className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
              <Users className="w-3.5 h-3.5" /> {entry.subscriber_count}
            </span>
            <span className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
              <GitFork className="w-3.5 h-3.5" /> {entry.fork_count}
            </span>
          </div>
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

      {/* Out-of-sample honesty row — real performance on post-publish data. */}
      <OutOfSampleRow entry={entry} />

      <div className="px-5 pb-4 mt-auto space-y-2">
        {subscribed ? (
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1 opacity-80 cursor-default" disabled>
              <CheckCircle2 className="w-4 h-4 text-emerald-500" /> Copying
            </Button>
            <Button
              variant="ghost"
              onClick={onUnsubscribe}
              loading={unsubscribing}
              className="text-xs font-semibold text-rose-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10 px-3"
            >
              Stop
            </Button>
          </div>
        ) : (
          <Button className="w-full" onClick={onCopy}>
            <Copy className="w-4 h-4" /> Copy Trade
          </Button>
        )}
        <div className="flex gap-2">
          <Button variant="secondary" className="flex-1" onClick={onFork} loading={forking}>
            <GitFork className="w-4 h-4" /> Fork
          </Button>
          {hasLineage && (
            <Button variant="secondary" className="flex-1" onClick={onLineage}>
              <Network className="w-4 h-4" /> Lineage
            </Button>
          )}
        </div>
      </div>
    </GlassCard>
  )
}

/* Out-of-sample scorecard: honest performance on data AFTER the publish date.
   Shows alpha decay by comparing OOS return against the in-sample number. */
function OutOfSampleRow({ entry }: { entry: LeaderboardEntry }) {
  if (!entry.oos_computed) {
    return (
      <div className="px-5 py-2 flex items-center gap-1.5 text-[10px] text-zinc-400
        bg-black/[0.015] dark:bg-white/[0.02] border-t border-black/[0.05] dark:border-white/[0.05]">
        <FlaskConical className="w-3 h-3" /> Out-of-sample: pending (needs post-publish data)
      </div>
    )
  }
  const inSample = entry.cagr_pct ?? entry.total_return_pct
  const oos = entry.oos_cagr_pct ?? entry.oos_total_return_pct
  const decayed = inSample != null && oos != null && oos < inSample
  return (
    <div className="px-5 py-2 flex items-center justify-between text-[10px]
      bg-black/[0.015] dark:bg-white/[0.02] border-t border-black/[0.05] dark:border-white/[0.05]">
      <span className="flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400">
        <FlaskConical className="w-3 h-3" /> Out-of-sample
      </span>
      <span className="flex items-center gap-2 tabular-nums">
        <span className={cn('font-semibold',
          (oos ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400')}>
          {fmtPct(oos, true)}
        </span>
        <span className="text-zinc-400">Sharpe {entry.oos_sharpe_ratio != null ? entry.oos_sharpe_ratio.toFixed(2) : '—'}</span>
        {decayed && (
          <span className="text-amber-500 flex items-center gap-0.5" title="Alpha decayed vs. in-sample">
            <TrendingDown className="w-3 h-3" /> decayed
          </span>
        )}
      </span>
    </div>
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
        accounts in real time. Requires at least 3 on-platform backtests, and we publish an
        out-of-sample scorecard on your listing to keep the commons honest.
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

/* ── Lineage (fork graph) modal ────────────────────────────────────────────── */
function LineageModal({ entry, onClose }: { entry: LeaderboardEntry; onClose: () => void }) {
  const [graph, setGraph] = useState<LineageResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.getLineage(entry.public_strategy_id)
      .then(setGraph)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Could not load lineage'))
  }, [entry.public_strategy_id])

  return (
    <Modal onClose={onClose}>
      <div className="flex items-center gap-2 mb-1">
        <Network className="w-5 h-5 text-violet-500" />
        <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Fork lineage</h3>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-5">
        The ancestry and descendants of “{entry.title}”. Each fork is an immutable
        snapshot — this is the graph of what was inherited and what improved on it.
      </p>

      {err && <p className="text-sm text-rose-500 mb-3">{err}</p>}
      {!graph ? (
        <div className="flex justify-center py-8 text-zinc-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
      ) : (
        <div className="space-y-5">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-400 mb-2">Descends from</p>
            {graph.ancestors.length === 0 ? (
              <p className="text-sm text-zinc-500">An original strategy — no ancestors.</p>
            ) : (
              <div className="space-y-1.5">
                {graph.ancestors.map((a, idx) => (
                  <div key={a.public_strategy_id} className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                    <GitBranch className="w-3.5 h-3.5 text-violet-400" style={{ marginLeft: idx * 12 }} />
                    {a.title}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-400 mb-2">
              Forks that were published ({graph.children.length})
            </p>
            {graph.children.length === 0 ? (
              <p className="text-sm text-zinc-500">No published forks yet.</p>
            ) : (
              <div className="space-y-2">
                {graph.children.map((c) => (
                  <div key={c.public_strategy_id}
                    className="flex items-center justify-between gap-2 rounded-lg px-3 py-2
                      bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.05] dark:border-white/[0.05]">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">{c.title}</p>
                      <p className="text-[11px] text-zinc-400">by {c.creator_name}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                        Sharpe {c.sharpe_ratio != null ? c.sharpe_ratio.toFixed(2) : '—'}
                      </p>
                      <p className={cn('text-[11px] font-semibold',
                        (c.cagr_pct ?? 0) >= (entry.cagr_pct ?? 0)
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-zinc-500')}>
                        {fmtPct(c.cagr_pct, true)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
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
