import Link from 'next/link'
import { GlassCard } from '@/components/ui/GlassCard'
import { Badge } from '@/components/ui/Badge'
import { ArrowRight, Clock } from 'lucide-react'
import type { Strategy } from '@/lib/types'
import { STATUS_BADGE } from '@/lib/constants'
import { fmtDate, fmtCurrency } from '@/lib/utils'

export function StrategyCard({ strategy: s }: { strategy: Strategy }) {
  const variant = STATUS_BADGE[s.status] ?? 'default'

  return (
    <Link href={`/strategies/${s.id}`} className="block h-full">
      <GlassCard hover padding="md" className="h-full flex flex-col group">
        <div className="flex items-start justify-between mb-3">
          <Badge variant={variant} dot pulse={s.status === 'active'}>
            {s.status}
          </Badge>
          <ArrowRight className="w-4 h-4 text-zinc-300 dark:text-zinc-600 group-hover:text-violet-500 group-hover:translate-x-0.5 transition-all duration-150" />
        </div>

        <h3 className="text-[15px] font-semibold text-zinc-900 dark:text-zinc-100 mb-1.5 line-clamp-1">{s.name}</h3>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed flex-1">{s.prompt}</p>

        <div className="flex items-center gap-1.5 flex-wrap mt-4">
          {s.symbols.map((sym) => (
            <span key={sym} className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-md bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              {sym}
            </span>
          ))}
          <span className="flex items-center gap-1 text-[11px] text-zinc-400 ml-auto">
            <Clock className="w-3 h-3" />{s.timeframe}
          </span>
        </div>

        <div className="mt-3 pt-3 border-t border-black/[0.05] dark:border-white/[0.05] flex items-center justify-between">
          <span className="text-[11px] text-zinc-400">{fmtDate(s.created_at ?? new Date().toISOString())}</span>
          <span className="text-[11px] text-zinc-400">{fmtCurrency(s.risk.max_order_notional)} cap</span>
        </div>
      </GlassCard>
    </Link>
  )
}
