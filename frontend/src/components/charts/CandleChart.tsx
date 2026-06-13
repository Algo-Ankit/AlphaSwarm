'use client'
import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '@/lib/types'
import { ema } from '@/lib/ta'

interface CandleChartProps {
  bars: Bar[]
  /** Latest live tick (same timestamp → updates last candle; newer → appends). */
  liveBar?: Bar | null
  dark: boolean
  height?: number
}

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

export function CandleChart({ bars, liveBar, dark, height = 420 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const ema20Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ema50Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const lastTimeRef = useRef<number>(0)

  // ── Build chart + load historical data ──────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    if (!container || bars.length === 0) return

    const textColor = dark ? '#a1a1aa' : '#52525b'
    const gridColor = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor, scaleMargins: { top: 0.06, bottom: 0.26 } },
      height,
      autoSize: true,
    })
    chartRef.current = chart

    const candles = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444', borderVisible: false,
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    })
    candleRef.current = candles

    const volume = chart.addHistogramSeries({
      priceScaleId: 'volume', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false,
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    volumeRef.current = volume

    const ema20 = chart.addLineSeries({ color: '#3b82f6', lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false })
    const ema50 = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false })
    ema20Ref.current = ema20
    ema50Ref.current = ema50

    const times = bars.map((b) => sec(b.timestamp))
    candles.setData(bars.map((b, i) => ({ time: times[i], open: b.open, high: b.high, low: b.low, close: b.close })))
    volume.setData(bars.map((b, i) => ({
      time: times[i], value: b.volume,
      color: b.close >= b.open ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)',
    })))

    const closes = bars.map((b) => b.close)
    const e20 = ema(closes, 20)
    const e50 = ema(closes, 50)
    ema20.setData(times.map((t, i) => ({ time: t, value: e20[i] })).filter((d) => !Number.isNaN(d.value)))
    ema50.setData(times.map((t, i) => ({ time: t, value: e50[i] })).filter((d) => !Number.isNaN(d.value)))

    lastTimeRef.current = times[times.length - 1] as number
    chart.timeScale().fitContent()

    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(container)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
      ema20Ref.current = null
      ema50Ref.current = null
    }
  }, [bars, dark, height])

  // ── Apply live tick incrementally (no full redraw) ──────────────────────
  useEffect(() => {
    if (!liveBar || !candleRef.current || !volumeRef.current) return
    const t = sec(liveBar.timestamp)
    if ((t as number) < lastTimeRef.current) return // ignore stale/out-of-order
    candleRef.current.update({ time: t, open: liveBar.open, high: liveBar.high, low: liveBar.low, close: liveBar.close })
    volumeRef.current.update({
      time: t, value: liveBar.volume,
      color: liveBar.close >= liveBar.open ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)',
    })
    lastTimeRef.current = t as number
  }, [liveBar])

  if (bars.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-zinc-400 dark:text-zinc-500" style={{ height }}>
        No market data available.
      </div>
    )
  }
  return <div ref={containerRef} className="w-full" style={{ height }} />
}
