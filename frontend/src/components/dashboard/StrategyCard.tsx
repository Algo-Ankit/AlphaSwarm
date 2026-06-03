import Link from 'next/link'
import { ArrowRight, Clock, Code2 } from 'lucide-react'
import type { Strategy } from '@/lib/types'
import { STATUS_BADGE } from '@/lib/constants'
import { Badge } from '@/components/ui/Badge'
import { fmtDate, fmtCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'

export function StrategyCard({ strategy: s }: { strategy: Strategy }) {
  const variant = STATUS_BADGE[s.status] ?? 'default'
  const isQuant = (s as { creation_mode?: string }).creation_mode === 'quant'

  return (
    <Link href={`/strategies/${s.id}`} className="block h-full group">
      <div className="glass-card h-full flex flex-col p-5 cursor-pointer">

        {/* Header row */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <Badge variant={variant} dot pulse={s.status === 'active'}>
              {s.status}
            </Badge>
            {isQuant && (
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md
                bg-emerald-100 text-emerald-700
                dark:bg-emerald-500/15 dark:text-emerald-300">
                <Code2 className="w-2.5 h-2.5" />
                Python
              </span>
            )}
          </div>
          <ArrowRight className={cn(
            'w-4 h-4 flex-shrink-0 transition-all duration-200',
            'text-zinc-300 dark:text-zinc-600',
            'group-hover:text-violet-600 dark:group-hover:text-violet-400',
            'group-hover:translate-x-0.5',
          )} />
        </div>

        {/* Name + prompt */}
        <h3 className="text-[15px] font-bold text-zinc-900 dark:text-zinc-100 mb-1.5 line-clamp-1 leading-snug">
          {s.name}
        </h3>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed flex-1">
          {s.prompt}
        </p>

        {/* Symbol chips */}
        <div className="flex items-center gap-1.5 flex-wrap mt-4">
          {s.symbols.map((sym) => (
            <span key={sym} className={cn(
              'text-[11px] font-mono font-semibold px-2 py-0.5 rounded-md leading-none',
              'bg-zinc-100 text-zinc-700 border border-zinc-200',
              'dark:bg-zinc-800/80 dark:text-zinc-300 dark:border-zinc-700',
            )}>
              {sym}
            </span>
          ))}
          <span className="flex items-center gap-1 text-[11px] text-zinc-400 dark:text-zinc-500 ml-auto font-medium">
            <Clock className="w-3 h-3" />{s.timeframe}
          </span>
        </div>

        {/* Footer */}
        <div className={cn(
          'mt-4 pt-3 flex items-center justify-between',
          'border-t border-zinc-100 dark:border-white/[0.05]',
        )}>
          <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
            {fmtDate(s.created_at ?? new Date().toISOString())}
          </span>
          <span className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400">
            {fmtCurrency(s.risk.max_order_notional)} cap
          </span>
        </div>
      </div>
    </Link>
  )
}
