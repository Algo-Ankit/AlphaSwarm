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
import type { BacktestBar, BacktestTrade } from '@/lib/types'

interface BacktestChartProps {
  bars: BacktestBar[]
  trades: BacktestTrade[]
  equityCurve: number[]
  theme: 'vs-dark' | 'light'
}

export function BacktestChart({ bars, trades, equityCurve, theme }: BacktestChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || bars.length === 0) return

    const isDark = theme === 'vs-dark'
    const textColor = isDark ? '#a1a1aa' : '#52525b'
    const gridColor = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)'

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor, scaleMargins: { top: 0.08, bottom: 0.32 } },
      height: 360,
      autoSize: true,
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceScaleId: 'right',
    })

    const times = bars.map((b) => Math.floor(new Date(b.timestamp).getTime() / 1000) as UTCTimestamp)

    candleSeries.setData(
      bars.map((b, i) => ({
        time: times[i],
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    )

    // Trade markers — fills happen at bar_index + 1's open
    const markers = trades
      .filter((t) => t.bar_index + 1 < times.length)
      .map((t) => ({
        time: times[t.bar_index + 1],
        position: (t.side === 'buy' ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
        color: t.side === 'buy' ? '#10b981' : '#ef4444',
        shape: (t.side === 'buy' ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
        text: `${t.side.toUpperCase()} ${Number(t.quantity)}`,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number))
    candleSeries.setMarkers(markers)

    // Equity curve — separate scale, bottom strip
    if (equityCurve.length === bars.length) {
      const equitySeries: ISeriesApi<'Line'> = chart.addLineSeries({
        color: '#8b5cf6',
        lineWidth: 2,
        priceScaleId: 'equity',
        lastValueVisible: true,
        priceLineVisible: false,
      })
      chart.priceScale('equity').applyOptions({
        scaleMargins: { top: 0.72, bottom: 0.02 },
        borderColor: gridColor,
      })
      equitySeries.setData(
        equityCurve.map((v, i) => ({ time: times[i], value: v })),
      )
    }

    chart.timeScale().fitContent()

    const resizeObserver = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect
      chart.applyOptions({ width })
    })
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [bars, trades, equityCurve, theme])

  if (bars.length === 0) return null

  return <div ref={containerRef} className="w-full" style={{ height: 360 }} />
}
