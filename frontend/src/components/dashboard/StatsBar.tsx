import { GlassCard } from '@/components/ui/GlassCard'
import { Zap, TrendingUp, Shield } from 'lucide-react'
import type { Strategy } from '@/lib/types'
import { cn } from '@/lib/utils'

export function StatsBar({ strategies }: { strategies: Strategy[] }) {
  const active = strategies.filter((s) => s.status === 'active').length
  const total = strategies.length
  const allPaper = strategies.every((s) => s.risk.paper_trading_only)

  const stats = [
    { label: 'Active Bots',       value: active,             icon: Zap,        color: 'text-violet-500', bg: 'bg-violet-50 dark:bg-violet-500/10' },
    { label: 'Total Strategies',  value: total,              icon: TrendingUp,  color: 'text-blue-500',   bg: 'bg-blue-50 dark:bg-blue-500/10' },
    { label: 'Trading Mode',      value: allPaper ? 'Paper' : 'Live', icon: Shield, color: allPaper ? 'text-emerald-500' : 'text-amber-500', bg: allPaper ? 'bg-emerald-50 dark:bg-emerald-500/10' : 'bg-amber-50 dark:bg-amber-500/10' },
  ]

  return (
    <div className="grid grid-cols-3 gap-4">
      {stats.map((s) => (
        <GlassCard key={s.label} padding="md">
          <div className="flex items-center gap-3">
            <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0', s.bg, s.color)}>
              <s.icon className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xl font-bold text-zinc-900 dark:text-zinc-100 leading-none">{s.value}</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">{s.label}</p>
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  )
}
