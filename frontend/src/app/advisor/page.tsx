'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { AppShell } from '@/components/layout/AppShell'
import { GlassCard } from '@/components/ui/GlassCard'
import { Button } from '@/components/ui/Button'
import { api, getAccessToken } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Sparkles, Send, User, AlertCircle } from 'lucide-react'

type Turn = {
  role: 'user' | 'advisor'
  content: string
}

const SUGGESTIONS = [
  'Analyze RELIANCE.NS',
  'SIP ₹5,000/month in NIFTYBEES for 10 years',
  'Is NVIDIA a good buy right now?',
  'Compare GOLDBEES vs SILVERBEES',
  'SWP plan for a ₹50L corpus',
]

/* react-markdown renders WITHOUT raw HTML by default; rehype-sanitize is layered
   on top so any <canvas>/<script> the advisor emits (per its Chart.js system
   prompt) is stripped rather than executed. Output stays plain, safe markdown. */
const MD_COMPONENTS = {
  h1: (p: any) => <h1 className="text-xl font-bold mt-5 mb-2 text-zinc-900 dark:text-zinc-50" {...p} />,
  h2: (p: any) => <h2 className="text-lg font-bold mt-5 mb-2 text-zinc-900 dark:text-zinc-50" {...p} />,
  h3: (p: any) => <h3 className="text-base font-semibold mt-4 mb-1.5 text-zinc-800 dark:text-zinc-100" {...p} />,
  p:  (p: any) => <p className="text-sm leading-relaxed my-2 text-zinc-700 dark:text-zinc-300" {...p} />,
  ul: (p: any) => <ul className="list-disc pl-5 my-2 space-y-1 text-sm text-zinc-700 dark:text-zinc-300" {...p} />,
  ol: (p: any) => <ol className="list-decimal pl-5 my-2 space-y-1 text-sm text-zinc-700 dark:text-zinc-300" {...p} />,
  li: (p: any) => <li className="leading-relaxed" {...p} />,
  strong: (p: any) => <strong className="font-semibold text-zinc-900 dark:text-zinc-100" {...p} />,
  a: (p: any) => <a className="text-violet-600 dark:text-violet-400 underline underline-offset-2" target="_blank" rel="noreferrer" {...p} />,
  // react-markdown v10 dropped the `inline` prop: block code carries a
  // `language-*` class or spans multiple lines; everything else is inline.
  code: ({ className, children, ...p }: any) => {
    const isBlock = /language-/.test(className || '') || /\n/.test(String(children))
    return isBlock
      ? <code className={cn('font-mono text-[0.82em]', className)} {...p}>{children}</code>
      : <code className="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-[0.85em] font-mono text-violet-700 dark:text-violet-300" {...p}>{children}</code>
  },
  pre: (p: any) => (
    <pre className="my-3 p-3.5 rounded-xl overflow-x-auto bg-zinc-950/95 dark:bg-black/60
      text-zinc-100 text-[0.82em] leading-relaxed border border-black/10 dark:border-white/10" {...p} />
  ),
  table: (p: any) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-black/[0.07] dark:border-white/[0.08]">
      <table className="w-full text-sm border-collapse" {...p} />
    </div>
  ),
  th: (p: any) => <th className="text-left font-semibold px-3 py-2 bg-zinc-50 dark:bg-white/[0.04] text-zinc-700 dark:text-zinc-200 border-b border-black/[0.07] dark:border-white/[0.08]" {...p} />,
  td: (p: any) => <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300 border-b border-black/[0.05] dark:border-white/[0.05]" {...p} />,
  blockquote: (p: any) => <blockquote className="border-l-2 border-violet-400 pl-3 my-2 text-sm italic text-zinc-600 dark:text-zinc-400" {...p} />,
  hr: () => <hr className="my-4 border-black/[0.07] dark:border-white/[0.08]" />,
}

function MarkdownView({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={MD_COMPONENTS}>
      {text}
    </ReactMarkdown>
  )
}

export default function AdvisorPage() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!getAccessToken()) router.replace('/login')
  }, [router])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, loading])

  async function submit(raw?: string) {
    const q = (raw ?? query).trim()
    if (!q || loading) return
    setError(null)
    setQuery('')
    setTurns((t) => [...t, { role: 'user', content: q }])
    setLoading(true)
    try {
      const { response } = await api.analyzeAdvisor(q)
      setTurns((t) => [...t, { role: 'advisor', content: response }])
    } catch (e) {
      setError((e as Error).message || 'The advisor could not complete your request.')
    } finally {
      setLoading(false)
    }
  }

  const empty = turns.length === 0

  return (
    <AppShell>
      <div className="flex flex-col" style={{ animation: 'fadeIn 0.2s ease-out' }}>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl flex-shrink-0
            bg-gradient-to-br from-emerald-500 to-emerald-700 shadow-[0_4px_18px_rgba(16,185,129,0.4)]">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight">
              AI Investment Advisor
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 font-medium">
              Stock & ETF analysis, SIP/SWP planning, and a clear verdict.
            </p>
          </div>
        </div>

        {/* Empty state with suggestions */}
        {empty && (
          <GlassCard padding="lg" className="text-center">
            <Sparkles className="w-8 h-8 mx-auto text-emerald-500 mb-3" />
            <p className="text-base font-bold text-zinc-900 dark:text-zinc-50">
              Ask about any stock, ETF, or investment plan
            </p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 mb-5">
              Global equities & ETFs (NSE/BSE, NYSE, NASDAQ, LSE) with full statistical analysis.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="px-3 py-1.5 rounded-full text-xs font-medium
                    bg-zinc-100 hover:bg-zinc-200 text-zinc-700
                    dark:bg-white/[0.05] dark:hover:bg-white/[0.1] dark:text-zinc-300
                    border border-black/[0.05] dark:border-white/[0.06] transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </GlassCard>
        )}

        {/* Conversation */}
        <div className="space-y-4">
          {turns.map((turn, i) =>
            turn.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="flex items-start gap-2.5 max-w-[80%]">
                  <div className="px-4 py-2.5 rounded-2xl rounded-tr-sm bg-violet-600 text-white text-sm font-medium shadow-sm">
                    {turn.content}
                  </div>
                  <div className="flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0
                    bg-gradient-to-br from-violet-400 to-violet-600 text-white">
                    <User className="w-4 h-4" />
                  </div>
                </div>
              </div>
            ) : (
              <GlassCard key={i} padding="lg" className="overflow-hidden">
                <MarkdownView text={turn.content} />
              </GlassCard>
            ),
          )}

          {loading && (
            <GlassCard padding="lg" className="flex items-center gap-3">
              <div className="flex gap-1">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce"
                    style={{ animationDelay: `${d * 0.15}s` }}
                  />
                ))}
              </div>
              <span className="text-sm text-zinc-500 dark:text-zinc-400 font-medium">
                Analyzing markets…
              </span>
            </GlassCard>
          )}

          {error && (
            <GlassCard padding="md" className="border-rose-300 dark:border-rose-500/25 bg-rose-50 dark:bg-rose-500/[0.06]">
              <div className="flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-bold text-rose-700 dark:text-rose-400">Advisor error</p>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-0.5">{error}</p>
                </div>
              </div>
            </GlassCard>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="sticky bottom-4 mt-6">
          <GlassCard padding="sm" className="flex items-end gap-2">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  submit()
                }
              }}
              rows={1}
              placeholder='e.g. "Analyze RELIANCE.NS" or "SIP 5000 in Nifty ETF"'
              className={cn(
                'flex-1 resize-none bg-transparent outline-none px-2 py-2 max-h-40',
                'text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-500',
              )}
            />
            <Button
              size="md"
              loading={loading}
              disabled={!query.trim()}
              onClick={() => submit()}
              className="flex-shrink-0"
            >
              <Send className="w-4 h-4" />
              Ask
            </Button>
          </GlassCard>
          <p className="text-[11px] text-zinc-400 dark:text-zinc-600 text-center mt-2">
            Not SEBI/SEC-registered advice. Projections assume consistent returns — actual returns vary.
          </p>
        </div>
      </div>
    </AppShell>
  )
}
