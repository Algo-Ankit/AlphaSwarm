'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { StrategyCard } from '@/components/dashboard/StrategyCard'
import { StatsBar } from '@/components/dashboard/StatsBar'
import { Button } from '@/components/ui/Button'
import { GlassCard } from '@/components/ui/GlassCard'
import { api, getAccessToken } from '@/lib/api'
import type { Strategy } from '@/lib/types'
import { Plus, Zap, Activity } from 'lucide-react'

function Skeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="glass-card h-48 animate-pulse opacity-40 rounded-3xl" />
      ))}
    </div>
  )
}

function Empty() {
  const router = useRouter()
  return (
    <div className="flex flex-col items-center justify-center py-32 text-center animate-slide-up relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-white/5 to-transparent">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-violet-500/10 via-transparent to-transparent opacity-50 blur-3xl pointer-events-none" />
      <div className="relative z-10">
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center mb-6 shadow-[0_0_40px_rgba(139,92,246,0.3)] hover:scale-110 transition-transform duration-500">
          <Zap className="w-10 h-10 text-white fill-white/20" />
        </div>
        <h2 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-500 dark:from-white dark:to-zinc-500 mb-3">No strategies yet</h2>
        <p className="text-base text-zinc-500 dark:text-zinc-400 mb-8 max-w-md mx-auto leading-relaxed">
          Describe your trading idea in plain English and let our advanced AI engine turn it into a high-performance live bot.
        </p>
        <Button size="lg" onClick={() => router.push('/strategies/new')} className="shadow-[0_0_20px_rgba(139,92,246,0.25)] hover:shadow-[0_0_30px_rgba(139,92,246,0.4)] transition-all duration-300">
          <Plus className="w-5 h-5 mr-2" />
          Build First Strategy
        </Button>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const router = useRouter()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace('/login')
      return
    }
    api.listStrategies()
      .then(setStrategies)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [router])

  return (
    <AppShell>
      <div className="space-y-10 animate-fade-in relative z-10">
        <div className="flex items-end justify-between">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-semibold tracking-wide uppercase mb-4">
              <Activity className="w-3.5 h-3.5" /> System Active
            </div>
            <h2 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-900 to-zinc-600 dark:from-white dark:to-zinc-400 tracking-tight">Good morning, Trader</h2>
            <p className="text-base text-zinc-500 dark:text-zinc-400 mt-2 font-medium">
              {strategies.length > 0
                ? `${strategies.filter((s) => s.status === 'active').length} active bots generating alpha.`
                : 'Ready to deploy your first strategy?'}
            </p>
          </div>
          {strategies.length > 0 && (
            <Button size="md" onClick={() => router.push('/strategies/new')} className="shadow-[0_0_15px_rgba(139,92,246,0.2)] hover:shadow-[0_0_25px_rgba(139,92,246,0.4)]">
              <Plus className="w-4 h-4 mr-2" />
              New Strategy
            </Button>
          )}
        </div>

        {strategies.length > 0 && <StatsBar strategies={strategies} />}

        {loading ? <Skeleton /> : error ? (
          <GlassCard padding="lg" className="text-center border-rose-500/20 bg-rose-500/5">
            <p className="text-base text-rose-600 dark:text-rose-400 font-semibold">Failed to load strategies</p>
            <p className="text-sm text-zinc-500 mt-2">{error}</p>
          </GlassCard>
        ) : strategies.length === 0 ? <Empty /> : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {strategies.map((s) => <StrategyCard key={s.id} strategy={s} />)}
          </div>
        )}
      </div>
    </AppShell>
  )
}

