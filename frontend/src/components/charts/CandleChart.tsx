'use client'
import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  PriceScaleMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '@/lib/types'
import { bollinger, ema, sma, vwap } from '@/lib/ta'

/** Which analysis overlays to draw on the price chart. */
export interface ChartOverlays {
  ema20: boolean
  ema50: boolean
  ema200: boolean
  sma50: boolean
  bb: boolean
  vwap: boolean
}

export const DEFAULT_OVERLAYS: ChartOverlays = {
  ema20: true,
  ema50: true,
  ema200: false,
  sma50: false,
  bb: false,
  vwap: false,
}

export const OVERLAY_META: { key: keyof ChartOverlays; label: string; color: string }[] = [
  { key: 'ema20', label: 'EMA 20', color: '#3b82f6' },
  { key: 'ema50', label: 'EMA 50', color: '#f59e0b' },
  { key: 'ema200', label: 'EMA 200', color: '#ec4899' },
  { key: 'sma50', label: 'SMA 50', color: '#14b8a6' },
  { key: 'bb', label: 'BB (20, 2)', color: '#8b5cf6' },
  { key: 'vwap', label: 'VWAP', color: '#eab308' },
]

interface CandleChartProps {
  bars: Bar[]
  /** Latest live tick (same timestamp → updates last candle; newer → appends). */
  liveBar?: Bar | null
  dark: boolean
  height?: number
  overlays?: ChartOverlays
  logScale?: boolean
}

interface HoverInfo {
  open: number
  high: number
  low: number
  close: number
  volume: number
  changePct: number | null
}

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp

const fmtN = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function CandleChart({
  bars, liveBar, dark, height = 420,
  overlays = DEFAULT_OVERLAYS, logScale = false,
}: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const lastTimeRef = useRef<number>(0)
  const [hover, setHover] = useState<HoverInfo | null>(null)

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
      rightPriceScale: {
        borderColor: gridColor,
        scaleMargins: { top: 0.06, bottom: 0.26 },
        mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
      },
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

    const times = bars.map((b) => sec(b.timestamp))
    candles.setData(bars.map((b, i) => ({ time: times[i], open: b.open, high: b.high, low: b.low, close: b.close })))
    volume.setData(bars.map((b, i) => ({
      time: times[i], value: b.volume,
      color: b.close >= b.open ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)',
    })))

    // ── Overlays ───────────────────────────────────────────────────────────
    const closes = bars.map((b) => b.close)
    const lineOpts = { lineWidth: 1 as const, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }
    const setLine = (series: ISeriesApi<'Line'>, vals: number[]) =>
      series.setData(times.map((t, i) => ({ time: t, value: vals[i] })).filter((d) => !Number.isNaN(d.value)))

    if (overlays.ema20) setLine(chart.addLineSeries({ ...lineOpts, color: '#3b82f6' }), ema(closes, 20))
    if (overlays.ema50) setLine(chart.addLineSeries({ ...lineOpts, color: '#f59e0b' }), ema(closes, 50))
    if (overlays.ema200) setLine(chart.addLineSeries({ ...lineOpts, color: '#ec4899' }), ema(closes, 200))
    if (overlays.sma50) setLine(chart.addLineSeries({ ...lineOpts, color: '#14b8a6' }), sma(closes, 50))
    if (overlays.bb) {
      const b = bollinger(closes, 20, 2)
      setLine(chart.addLineSeries({ ...lineOpts, color: 'rgba(139,92,246,0.7)' }), b.upper)
      setLine(chart.addLineSeries({ ...lineOpts, color: 'rgba(139,92,246,0.35)', lineStyle: LineStyle.Dashed }), b.middle)
      setLine(chart.addLineSeries({ ...lineOpts, color: 'rgba(139,92,246,0.7)' }), b.lower)
    }
    if (overlays.vwap) {
      const v = vwap(bars.map((b) => b.high), bars.map((b) => b.low), closes, bars.map((b) => b.volume))
      setLine(chart.addLineSeries({ ...lineOpts, color: '#eab308', lineWidth: 2 }), v)
    }

    // ── Crosshair OHLC readout ────────────────────────────────────────────
    // Map time → bar index for prev-close change computation.
    const idxByTime = new Map<number, number>()
    times.forEach((t, i) => idxByTime.set(t as number, i))

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) { setHover(null); return }
      const i = idxByTime.get(param.time as number)
      if (i === undefined) { setHover(null); return }
      const b = bars[i]
      const prev = i > 0 ? bars[i - 1].close : null
      setHover({
        open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
        changePct: prev ? ((b.close - prev) / prev) * 100 : null,
      })
    })

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
      setHover(null)
    }
  }, [bars, dark, height, overlays, logScale])

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

  const info = hover ?? (() => {
    const b = bars[bars.length - 1]
    const prev = bars.length > 1 ? bars[bars.length - 2].close : null
    return {
      open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
      changePct: prev ? ((b.close - prev) / prev) * 100 : null,
    }
  })()
  const up = info.close >= info.open

  return (
    <div className="relative">
      {/* OHLC readout — tracks the crosshair, falls back to the latest bar */}
      <div className="absolute top-2 left-3 z-10 flex items-center gap-3 px-2.5 py-1 rounded-lg
        bg-white/70 dark:bg-zinc-900/70 backdrop-blur-sm text-[11px] font-mono tabular-nums
        pointer-events-none select-none">
        <span className="text-zinc-400">O <span className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>{fmtN(info.open)}</span></span>
        <span className="text-zinc-400">H <span className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>{fmtN(info.high)}</span></span>
        <span className="text-zinc-400">L <span className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>{fmtN(info.low)}</span></span>
        <span className="text-zinc-400">C <span className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>{fmtN(info.close)}</span></span>
        {info.changePct != null && (
          <span className={info.changePct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>
            {info.changePct >= 0 ? '+' : ''}{info.changePct.toFixed(2)}%
          </span>
        )}
        <span className="text-zinc-400">Vol <span className="text-zinc-600 dark:text-zinc-300">{Math.round(info.volume).toLocaleString('en-US')}</span></span>
      </div>
      <div ref={containerRef} className="w-full" style={{ height }} />
    </div>
  )
}
