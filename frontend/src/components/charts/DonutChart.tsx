'use client'
import type { AllocationSlice } from '@/lib/types'
import { cn } from '@/lib/utils'

interface Props {
  slices: AllocationSlice[]
  size?: number
  thickness?: number
  className?: string
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, endAngle)
  const end   = polarToCartesian(cx, cy, r, startAngle)
  const large = endAngle - startAngle > 180 ? 1 : 0
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 0 ${end.x} ${end.y}`
}

export function DonutChart({ slices, size = 160, thickness = 28, className }: Props) {
  const cx = size / 2
  const cy = size / 2
  const r  = (size - thickness) / 2

  // Nothing to show — render an empty ring placeholder
  if (slices.length === 0) {
    return (
      <div className={cn('flex flex-col items-center', className)}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor"
            strokeWidth={thickness} className="text-zinc-200 dark:text-zinc-800" />
          <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central"
            className="fill-zinc-400 dark:fill-zinc-500 text-[10px]" fontSize="10">
            No data
          </text>
        </svg>
      </div>
    )
  }

  const total = slices.reduce((s, sl) => s + sl.value, 0) || 1
  let cursor = 0
  const paths: { d: string; color: string; label: string; pct: number }[] = []

  for (const sl of slices) {
    const sweep = (sl.value / total) * 360
    if (sweep < 0.5) { cursor += sweep; continue }  // skip tiny slivers
    paths.push({
      d: arcPath(cx, cy, r, cursor, cursor + sweep),
      color: sl.color,
      label: sl.label,
      pct: sl.pct,
    })
    cursor += sweep
  }

  const largest = slices.reduce((a, b) => (a.value > b.value ? a : b), slices[0])

  return (
    <div className={cn('flex flex-col items-center gap-4', className)}>
      <div className="relative">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Background ring */}
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor"
            strokeWidth={thickness} className="text-zinc-100 dark:text-zinc-800" />
          {/* Arcs */}
          {paths.map((p, i) => (
            <path key={i} d={p.d} fill="none" stroke={p.color}
              strokeWidth={thickness - 2} strokeLinecap="round" />
          ))}
          {/* Center label */}
          <text x={cx} y={cy - 6} textAnchor="middle" dominantBaseline="central"
            fontSize="11" fontWeight="700" fill="currentColor"
            className="fill-zinc-800 dark:fill-zinc-100">
            {largest.pct.toFixed(0)}%
          </text>
          <text x={cx} y={cy + 9} textAnchor="middle" dominantBaseline="central"
            fontSize="9" fill="currentColor" className="fill-zinc-500 dark:fill-zinc-400">
            {largest.label}
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="space-y-1.5 w-full">
        {slices.map((sl) => (
          <div key={sl.label} className="flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: sl.color }} />
              <span className="text-zinc-600 dark:text-zinc-400 truncate">{sl.label}</span>
            </div>
            <span className="font-semibold text-zinc-800 dark:text-zinc-200 tabular-nums flex-shrink-0">
              {sl.pct.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
