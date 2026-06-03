import { Zap, TrendingUp, Shield } from 'lucide-react'
import type { Strategy } from '@/lib/types'
import { cn } from '@/lib/utils'

interface Stat {
  label: string
  value: string | number
  icon: typeof Zap
  colorLight: string
  colorDark: string
  bgLight: string
  bgDark: string
  glowDark: string
}

export function StatsBar({ strategies }: { strategies: Strategy[] }) {
  const active  = strategies.filter((s) => s.status === 'active').length
  const total   = strategies.length
  const allPaper = strategies.every((s) => s.risk.paper_trading_only)

  const stats: Stat[] = [
    {
      label: 'Active Bots',
      value: active,
      icon: Zap,
      colorLight: 'text-violet-700',
      colorDark:  'text-violet-300',
      bgLight:    'bg-violet-100',
      bgDark:     'dark:bg-violet-500/15',
      glowDark:   'dark:shadow-[0_0_12px_rgba(139,92,246,0.3)]',
    },
    {
      label: 'Total Strategies',
      value: total,
      icon: TrendingUp,
      colorLight: 'text-sky-700',
      colorDark:  'text-sky-300',
      bgLight:    'bg-sky-100',
      bgDark:     'dark:bg-sky-500/15',
      glowDark:   'dark:shadow-[0_0_12px_rgba(56,189,248,0.25)]',
    },
    {
      label: 'Mode',
      value: allPaper ? 'Paper' : 'Live',
      icon: Shield,
      colorLight: allPaper ? 'text-emerald-700' : 'text-amber-700',
      colorDark:  allPaper ? 'text-emerald-300' : 'text-amber-300',
      bgLight:    allPaper ? 'bg-emerald-100'   : 'bg-amber-100',
      bgDark:     allPaper ? 'dark:bg-emerald-500/15' : 'dark:bg-amber-500/15',
      glowDark:   allPaper ? 'dark:shadow-[0_0_12px_rgba(52,211,153,0.3)]' : 'dark:shadow-[0_0_12px_rgba(251,191,36,0.3)]',
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-4">
      {stats.map((s) => (
        <div
          key={s.label}
          className="glass-card p-5 flex items-center gap-4"
        >
          <div className={cn(
            'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-shadow',
            s.bgLight, s.bgDark, s.colorLight, s.colorDark, s.glowDark,
          )}>
            <s.icon className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className={cn(
              'text-2xl font-bold leading-none stat-num',
              s.colorLight, s.colorDark,
            )}>
              {s.value}
            </p>
            <p className="text-xs text-zinc-500 dark:text-zinc-500 mt-1 font-medium">{s.label}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
