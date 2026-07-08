'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '@/lib/types'
import { macd } from '@/lib/ta'

interface MacdPaneProps {
  bars: Bar[]
  dark: boolean
  height?: number
}

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

export function MacdPane({ bars, dark, height = 130 }: MacdPaneProps) {
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

    const closes = bars.map((b) => b.close)
    const times = bars.map((b) => sec(b.timestamp))
    const { macdLine, signalLine, histogram } = macd(closes)

    const hist = chart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false })
    hist.setData(
      times
        .map((t, i) => ({
          time: t,
          value: histogram[i],
          color: histogram[i] >= 0 ? 'rgba(16,185,129,0.55)' : 'rgba(239,68,68,0.55)',
        }))
        .filter((d) => !Number.isNaN(d.value)),
    )

    const macdSeries = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1, priceLineVisible: false, lastValueVisible: true })
    macdSeries.setData(times.map((t, i) => ({ time: t, value: macdLine[i] })).filter((d) => !Number.isNaN(d.value)))

    const signalSeries = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    signalSeries.setData(times.map((t, i) => ({ time: t, value: signalLine[i] })).filter((d) => !Number.isNaN(d.value)))

    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(container)

    return () => { ro.disconnect(); chart.remove() }
  }, [bars, dark, height])

  if (bars.length === 0) return null
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 mb-1 px-1">
        MACD (12, 26, 9) <span className="normal-case font-medium tracking-normal">· <span className="text-blue-500">line</span> / <span className="text-amber-500">signal</span></span>
      </p>
      <div ref={containerRef} className="w-full" style={{ height }} />
    </div>
  )
}
