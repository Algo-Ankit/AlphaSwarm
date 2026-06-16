'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { StrategyCard } from '@/components/dashboard/StrategyCard'
import { StatsBar } from '@/components/dashboard/StatsBar'
import { PortfolioOverview } from '@/components/dashboard/PortfolioOverview'
import { GoalWizard } from '@/components/dashboard/GoalWizard'
import { Button } from '@/components/ui/Button'
import { GlassCard } from '@/components/ui/GlassCard'
import { api, getAccessToken, getUserProfile } from '@/lib/api'
import type { Strategy } from '@/lib/types'
import { Plus, Activity } from 'lucide-react'
import { cn } from '@/lib/utils'

function Skeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {[1, 2, 3].map((i) => (
        <div key={i} className="glass-card h-52 animate-pulse" style={{ opacity: 0.5 }} />
      ))}
    </div>
  )
}

function greetingFor(date: Date): string {
  const h = date.getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function DashboardPage() {
  const router = useRouter()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Resolved from the authenticated user profile, not hardcoded. Set on mount
  // (client-only) to avoid an SSR/client hydration mismatch on the name + clock.
  const [greeting, setGreeting] = useState<string>('Welcome')

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace('/login')
      return
    }
    const profile = getUserProfile()
    const firstName = profile?.display_name?.trim().split(/\s+/)[0]
    setGreeting(`${greetingFor(new Date())}${firstName ? `, ${firstName}` : ''}`)
    api.listStrategies()
      .then(setStrategies)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [router])

  const activeCount = strategies.filter((s) => s.status === 'active').length

  return (
    <AppShell>
      <div className="space-y-8" style={{ animation: 'fadeIn 0.2s ease-out' }}>

        {/* Header */}
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className={cn(
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full mb-4',
              'text-[11px] font-bold uppercase tracking-widest',
              'bg-violet-100 text-violet-700 border border-violet-200',
              'dark:bg-violet-500/12 dark:text-violet-300 dark:border-violet-500/20',
            )}>
              <Activity className="w-3 h-3" />
              System Active
            </div>
            <h1 className="text-4xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight">
              {greeting}
            </h1>
            <p className="text-base text-zinc-500 dark:text-zinc-400 mt-1.5 font-medium">
              {strategies.length > 0
                ? activeCount > 0
                  ? `${activeCount} bot${activeCount > 1 ? 's' : ''} running — generating alpha right now.`
                  : `${strategies.length} strateg${strategies.length > 1 ? 'ies' : 'y'} ready to deploy.`
                : 'What will you trade today?'}
            </p>
          </div>

          {strategies.length > 0 && (
            <Button size="md" onClick={() => router.push('/strategies/new')}
              className="flex-shrink-0 shadow-[0_4px_14px_rgba(109,40,217,0.3)] hover:shadow-[0_6px_22px_rgba(109,40,217,0.45)]">
              <Plus className="w-4 h-4 mr-1.5" />
              New Strategy
            </Button>
          )}
        </div>

        {/* Stats */}
        {strategies.length > 0 && <StatsBar strategies={strategies} />}

        {/* Live portfolio (WS equity curve + P&L) */}
        {strategies.length > 0 && <PortfolioOverview />}

        {/* Content */}
        {loading ? (
          <Skeleton />
        ) : error ? (
          <GlassCard padding="lg" className="text-center border-rose-300 dark:border-rose-500/25 bg-rose-50 dark:bg-rose-500/06">
            <p className="text-base font-bold text-rose-700 dark:text-rose-400">Failed to load strategies</p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1.5">{error}</p>
          </GlassCard>
        ) : strategies.length === 0 ? (
          <GoalWizard onBuild={() => router.push('/strategies/new')} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {strategies.map((s) => <StrategyCard key={s.id} strategy={s} />)}
          </div>
        )}
      </div>
    </AppShell>
  )
}
