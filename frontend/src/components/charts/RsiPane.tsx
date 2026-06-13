'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '@/lib/types'
import { rsi } from '@/lib/ta'

interface RsiPaneProps {
  bars: Bar[]
  dark: boolean
  period?: number
  height?: number
}

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

export function RsiPane({ bars, dark, period = 14, height = 130 }: RsiPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || bars.length === 0) return

    const textColor = dark ? '#a1a1aa' : '#52525b'
    const gridColor = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'

    const chart: IChartApi = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor, fontSize: 10, fontFamily: "'JetBrains Mono', monospace" },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor },
      height,
      autoSize: true,
    })

    const line = chart.addLineSeries({ color: '#8b5cf6', lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
    line.createPriceLine({ price: 70, color: 'rgba(239,68,68,0.5)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '70' })
    line.createPriceLine({ price: 30, color: 'rgba(16,185,129,0.5)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: '30' })

    const closes = bars.map((b) => b.close)
    const r = rsi(closes, period)
    line.setData(
      bars
        .map((b, i) => ({ time: sec(b.timestamp), value: r[i] }))
        .filter((d) => !Number.isNaN(d.value)),
    )
    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(container)

    return () => { ro.disconnect(); chart.remove() }
  }, [bars, dark, period, height])

  if (bars.length === 0) return null
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-1 px-1">
        RSI ({period})
      </p>
      <div ref={containerRef} className="w-full" style={{ height }} />
    </div>
  )
}
