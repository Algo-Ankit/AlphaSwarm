'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { PortfolioSnapshot } from '@/lib/types'

interface EquityCurveProps {
  snapshots: PortfolioSnapshot[]
  dark: boolean
  height?: number
}

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

export function EquityCurve({ snapshots, dark, height = 240 }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || snapshots.length === 0) return

    const textColor = dark ? '#a1a1aa' : '#52525b'
    const gridColor = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'

    const chart: IChartApi = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor },
      height,
      autoSize: true,
    })

    const area = chart.addAreaSeries({
      lineColor: '#8b5cf6',
      topColor: 'rgba(139,92,246,0.35)',
      bottomColor: 'rgba(139,92,246,0.02)',
      lineWidth: 2,
      priceLineVisible: false,
    })
    // De-dupe by timestamp (lightweight-charts requires strictly ascending time).
    const seen = new Set<number>()
    const data = snapshots
      .map((s) => ({ time: sec(s.snapshot_time), value: s.total_equity }))
      .filter((d) => {
        const t = d.time as number
        if (seen.has(t)) return false
        seen.add(t)
        return true
      })
    area.setData(data)
    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(container)
    return () => { ro.disconnect(); chart.remove() }
  }, [snapshots, dark, height])

  if (snapshots.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-zinc-400 dark:text-zinc-500" style={{ height }}>
        No portfolio history yet — snapshots appear once a strategy runs.
      </div>
    )
  }
  return <div ref={containerRef} className="w-full" style={{ height }} />
}
