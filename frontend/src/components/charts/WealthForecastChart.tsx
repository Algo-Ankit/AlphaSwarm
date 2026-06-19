'use client'
import { useEffect, useRef } from 'react'
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
  Legend,
  type ChartConfiguration,
} from 'chart.js'
import type { WealthForecast } from '@/lib/types'

// Register only the pieces we use — keeps the bundle lean (Chart.js is tree-shakeable).
Chart.register(
  LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, Legend,
)

interface Props {
  forecast: WealthForecast
  dark: boolean
  /** Currency symbol for axis/tooltip formatting. */
  currency?: string
  height?: number
}

function compact(n: number, currency: string): string {
  const abs = Math.abs(n)
  if (abs >= 1e7) return `${currency}${(n / 1e7).toFixed(2)}Cr`
  if (abs >= 1e5) return `${currency}${(n / 1e5).toFixed(2)}L`
  if (abs >= 1e3) return `${currency}${(n / 1e3).toFixed(1)}K`
  return `${currency}${n.toFixed(0)}`
}

export function WealthForecastChart({ forecast, dark, currency = '₹', height = 360 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const grid = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
    const tick = dark ? '#a1a1aa' : '#52525b'

    const labels = forecast.projections.map((p) => (p.year === 0 ? 'Now' : `Yr ${p.year}`))

    const cfg: ChartConfiguration<'line'> = {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Optimistic (90th pct)',
            data: forecast.projections.map((p) => p.optimistic),
            borderColor: '#10b981',
            backgroundColor: 'rgba(16,185,129,0.10)',
            fill: '+1',           // fill down to the median line → confidence band
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderWidth: 2,
          },
          {
            label: 'Median (50th pct)',
            data: forecast.projections.map((p) => p.median),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.10)',
            fill: '+1',           // fill down to the pessimistic line
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderWidth: 2.5,
          },
          {
            label: 'Pessimistic (10th pct)',
            data: forecast.projections.map((p) => p.pessimistic),
            borderColor: '#ef4444',
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderWidth: 2,
          },
          {
            label: 'Total Invested',
            data: forecast.projections.map((p) => p.contributed),
            borderColor: dark ? '#71717a' : '#a1a1aa',
            borderDash: [5, 4],
            backgroundColor: 'transparent',
            fill: false,
            tension: 0,
            pointRadius: 0,
            pointHoverRadius: 4,
            borderWidth: 1.5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            labels: { color: tick, usePointStyle: true, boxWidth: 8, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${compact(ctx.parsed.y ?? 0, currency)}`,
            },
          },
        },
        scales: {
          x: { grid: { color: grid }, ticks: { color: tick, font: { size: 11 } } },
          y: {
            grid: { color: grid },
            ticks: { color: tick, font: { size: 11 }, callback: (v) => compact(Number(v), currency) },
          },
        },
      },
    }

    chartRef.current = new Chart(canvas, cfg)
    return () => { chartRef.current?.destroy(); chartRef.current = null }
  }, [forecast, dark, currency])

  return (
    <div style={{ height }}>
      <canvas ref={canvasRef} />
    </div>
  )
}
