'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api, getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { SocialPost } from '@/lib/types'
import {
  Rss, TrendingUp, TrendingDown, Heart, AlertCircle,
  Loader2, Copy, CheckCircle2, BadgeCheck, Send, ChevronDown,
} from 'lucide-react'

const fmtCagr = (n: number | null) =>
  n == null ? null : `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`

const fmtTime = (iso: string) => {
  const d = new Date(iso)
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function FeedPage() {
  const router = useRouter()
  const [posts, setPosts] = useState<SocialPost[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const offsetRef = useRef(0)
  const PAGE = 20

  const load = useCallback(async (reset = false) => {
    const off = reset ? 0 : offsetRef.current
    if (!reset) setLoadingMore(true)
    try {
      const rows = await api.getFeedTimeline({ limit: PAGE, offset: off })
      setPosts((prev) => reset ? rows : [...prev, ...rows])
      offsetRef.current = off + rows.length
      setHasMore(rows.length === PAGE)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load feed')
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    if (!getAccessToken()) { router.replace('/login'); return }
    load(true)
  }, [router, load])

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto space-y-4">
        {/* ── Header ─────────────────────────────────────── */}
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl
            bg-gradient-to-br from-violet-500 to-violet-700 shadow-[0_4px_18px_rgba(124,58,237,0.45)]">
            <Rss className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              Swarm Feed
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Updates from creators — subscribed strategies surface first.
            </p>
          </div>
        </div>

        {/* ── Compose ────────────────────────────────────── */}
        <ComposeBox onPosted={() => load(true)} />

        {error && (
          <GlassCard className="flex items-center gap-2 text-sm text-rose-600 dark:text-rose-400">
            <AlertCircle className="w-4 h-4" /> {error}
          </GlassCard>
        )}

        {/* ── Feed ───────────────────────────────────────── */}
        {loading ? (
          <div className="flex items-center justify-center py-24 text-zinc-400">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : posts.length === 0 ? (
          <GlassCard padding="lg" className="text-center py-14">
            <Rss className="w-10 h-10 mx-auto text-zinc-300 dark:text-zinc-700 mb-3" />
            <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">No posts yet</p>
            <p className="text-xs text-zinc-400 mt-1">
              Be the first to post an update or subscribe to a strategy on the Leaderboard.
            </p>
          </GlassCard>
        ) : (
          <>
            <div className="space-y-3">
              {posts.map((p) => <PostCard key={p.id} post={p} onCopy={() => load(true)} />)}
            </div>

            {hasMore && (
              <div className="flex justify-center pt-2">
                <Button
                  variant="secondary"
                  onClick={() => load()}
                  loading={loadingMore}
                >
                  <ChevronDown className="w-4 h-4" /> Load more
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}

/* ── Compose box ───────────────────────────────────────────────────────────── */
function ComposeBox({ onPosted }: { onPosted: () => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const limit = 5000

  const submit = async () => {
    if (!text.trim()) return
    setBusy(true); setErr(null)
    try {
      await api.createPost({ content_markdown: text.trim() })
      setText('')
      onPosted()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not post')
    } finally {
      setBusy(false)
    }
  }

  return (
    <GlassCard padding="md">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, limit))}
        placeholder="Share an update, insight, or milestone with the Swarm…"
        rows={3}
        className="w-full resize-none bg-transparent text-sm text-zinc-800 dark:text-zinc-200
          placeholder:text-zinc-400 focus:outline-none"
      />
      <div className="flex items-center justify-between mt-3 pt-3
        border-t border-black/[0.06] dark:border-white/[0.06]">
        <span className={cn(
          'text-xs tabular-nums',
          text.length > limit * 0.9
            ? 'text-rose-500'
            : 'text-zinc-400',
        )}>
          {text.length}/{limit}
        </span>
        <div className="flex items-center gap-2">
          {err && (
            <span className="text-xs text-rose-500 flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" /> {err}
            </span>
          )}
          <Button onClick={submit} loading={busy} disabled={!text.trim()}>
            <Send className="w-3.5 h-3.5" /> Post
          </Button>
        </div>
      </div>
    </GlassCard>
  )
}

/* ── Post card ─────────────────────────────────────────────────────────────── */
function PostCard({ post, onCopy }: { post: SocialPost; onCopy: () => void }) {
  const [copying, setCopying] = useState(false)
  const [copyErr, setCopyErr] = useState<string | null>(null)
  const [liked, setLiked] = useState(post.liked_by_me)
  const [likes, setLikes] = useState(post.likes_count)
  const [liking, setLiking] = useState(false)

  const handleLike = async () => {
    if (liking) return
    setLiking(true)
    // Optimistic flip; reconcile with the server's authoritative count.
    setLiked(!liked)
    setLikes((n) => n + (liked ? -1 : 1))
    try {
      const res = await api.togglePostLike(post.id)
      setLiked(res.liked)
      setLikes(res.likes_count)
    } catch {
      setLiked(liked)
      setLikes(post.likes_count)
    } finally {
      setLiking(false)
    }
  }

  const handleCopy = async () => {
    if (!post.public_strategy_id) return
    setCopying(true); setCopyErr(null)
    try {
      await api.subscribeStrategy(post.public_strategy_id, 50000)
      onCopy()
    } catch (e) {
      setCopyErr(e instanceof Error ? e.message : 'Could not copy')
    } finally {
      setCopying(false)
    }
  }

  const cagr = fmtCagr(post.cagr_pct)

  return (
    <GlassCard padding="none" className="overflow-hidden">
      {/* Subscribed accent bar */}
      {post.is_subscribed && (
        <div className="h-0.5 w-full bg-gradient-to-r from-violet-500 to-violet-400" />
      )}

      <div className="px-5 pt-4 pb-1">
        {/* Author row */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center
              bg-gradient-to-br from-violet-400 to-violet-600 text-[11px] font-bold text-white
              shadow-[0_2px_10px_rgba(124,58,237,0.3)]">
              {post.author_name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50 truncate">
                  {post.author_name}
                </span>
                {post.is_subscribed && (
                  <BadgeCheck className="w-3.5 h-3.5 text-violet-500 flex-shrink-0" />
                )}
              </div>
              <span className="text-[11px] text-zinc-400">{fmtTime(post.created_at)}</span>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="prose prose-sm dark:prose-invert max-w-none
          prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-code:text-violet-600
          dark:prose-code:text-violet-400 text-zinc-700 dark:text-zinc-300">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
            {post.content_markdown}
          </ReactMarkdown>
        </div>
      </div>

      {/* Strategy mini-widget */}
      {post.public_strategy_id && post.strategy_title && (
        <div className="mx-5 mb-4 mt-3 rounded-xl border border-black/[0.07] dark:border-white/[0.07]
          bg-zinc-50 dark:bg-zinc-900/60 overflow-hidden">
          <div className="px-4 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold text-zinc-700 dark:text-zinc-200 truncate">
                {post.strategy_title}
              </p>
              <div className="flex items-center gap-3 mt-1">
                {cagr && (
                  <span className={cn(
                    'flex items-center gap-0.5 text-xs font-bold tabular-nums',
                    post.cagr_pct! >= 0
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-rose-600 dark:text-rose-400',
                  )}>
                    {post.cagr_pct! >= 0
                      ? <TrendingUp className="w-3 h-3" />
                      : <TrendingDown className="w-3 h-3" />}
                    {cagr} 1Y CAGR
                  </span>
                )}
                {post.sharpe_ratio != null && (
                  <span className="text-xs text-zinc-400 tabular-nums">
                    Sharpe {post.sharpe_ratio.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            <Button
              variant="secondary"
              onClick={handleCopy}
              loading={copying}
              className="flex-shrink-0 text-xs"
            >
              <Copy className="w-3 h-3" /> Copy Trade
            </Button>
          </div>
          {copyErr && (
            <p className="px-4 pb-2 text-xs text-rose-500 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> {copyErr}
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-5 pb-3 flex items-center gap-4 border-t border-black/[0.04] dark:border-white/[0.04]">
        <button
          onClick={handleLike}
          disabled={liking}
          aria-pressed={liked}
          className={cn(
            'flex items-center gap-1.5 pt-2 text-xs transition-colors',
            liked
              ? 'text-rose-500 dark:text-rose-400'
              : 'text-zinc-400 hover:text-rose-500 dark:hover:text-rose-400',
          )}
        >
          <Heart className={cn('w-3.5 h-3.5', liked && 'fill-current')} />
          {likes > 0 ? likes : ''}
        </button>
        {post.is_subscribed && (
          <span className="flex items-center gap-1 pt-2 text-xs text-violet-500">
            <CheckCircle2 className="w-3 h-3" /> Copying
          </span>
        )}
      </div>
    </GlassCard>
  )
}
