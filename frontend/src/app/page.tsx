'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/AppShell'
import { StrategyCard } from '@/components/dashboard/StrategyCard'
import { StatsBar } from '@/components/dashboard/StatsBar'
import { Button } from '@/components/ui/Button'
import { GlassCard } from '@/components/ui/GlassCard'
import { api } from '@/lib/api'
import type { Strategy } from '@/lib/types'
import { Plus, Zap } from 'lucide-react'

function Skeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {[1, 2, 3].map((i) => (
        <div key={i} className="glass-card h-44 animate-pulse opacity-60" />
      ))}
    </div>
  )
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-400 to-violet-700 flex items-center justify-center mb-5 shadow-lg shadow-violet-500/25">
        <Zap className="w-8 h-8 text-white" />
      </div>
      <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100 mb-2">No strategies yet</h2>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-7 max-w-xs leading-relaxed">
        Describe your trading idea in plain English and let the AI turn it into a live bot.
      </p>
      <Link href="/strategies/new">
        <Button size="lg"><Plus className="w-5 h-5" />Build First Strategy</Button>
      </Link>
    </div>
  )
}

export default function DashboardPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listStrategies()
      .then(setStrategies)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <AppShell>
      <div className="space-y-8 animate-fade-in">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">Good morning, Trader</h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
              {strategies.length > 0
                ? `${strategies.filter((s) => s.status === 'active').length} active bots running.`
                : 'Ready to deploy your first strategy?'}
            </p>
          </div>
          {strategies.length > 0 && (
            <Link href="/strategies/new">
              <Button size="sm"><Plus className="w-4 h-4" />New Strategy</Button>
            </Link>
          )}
        </div>

        {strategies.length > 0 && <StatsBar strategies={strategies} />}

        {loading ? <Skeleton /> : error ? (
          <GlassCard padding="md" className="text-center">
            <p className="text-sm text-rose-600 dark:text-rose-400 font-medium">{error}</p>
            <p className="text-xs text-zinc-400 mt-1">Make sure the backend is running on port 8000.</p>
          </GlassCard>
        ) : strategies.length === 0 ? <Empty /> : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {strategies.map((s) => <StrategyCard key={s.id} strategy={s} />)}
          </div>
        )}
      </div>
    </AppShell>
  )
}
