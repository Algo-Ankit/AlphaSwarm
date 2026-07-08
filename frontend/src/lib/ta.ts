/**
 * DISPLAY-ONLY technical indicators for the charting layer.
 *
 * These power the terminal's visual overlays/sub-charts only. They are NOT used
 * for any trading decision — strategy and risk logic compute indicators with
 * pandas-ta on the backend (CLAUDE.md hard rule). Kept simple and dependency-free.
 */

/** Exponential moving average. Returns NaN for the warm-up period (i < period-1). */
export function ema(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN)
  if (values.length < period) return out
  const k = 2 / (period + 1)
  // Seed with the SMA of the first `period` values.
  let prev = 0
  for (let i = 0; i < period; i++) prev += values[i]
  prev /= period
  out[period - 1] = prev
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

/** Simple moving average. Returns NaN for the warm-up period. */
export function sma(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN)
  if (values.length < period) return out
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

/** Bollinger Bands: SMA(period) ± k·σ (population stdev over the window). */
export function bollinger(
  values: number[],
  period = 20,
  k = 2,
): { upper: number[]; middle: number[]; lower: number[] } {
  const middle = sma(values, period)
  const upper: number[] = new Array(values.length).fill(NaN)
  const lower: number[] = new Array(values.length).fill(NaN)
  for (let i = period - 1; i < values.length; i++) {
    let sq = 0
    for (let j = i - period + 1; j <= i; j++) sq += (values[j] - middle[i]) ** 2
    const sd = Math.sqrt(sq / period)
    upper[i] = middle[i] + k * sd
    lower[i] = middle[i] - k * sd
  }
  return { upper, middle, lower }
}

/**
 * VWAP over the loaded window (cumulative Σ(typical·vol) / Σvol).
 * Note: intraday traders usually want session-anchored VWAP; over a daily
 * window this reads as an anchored VWAP from the first loaded bar.
 */
export function vwap(
  highs: number[],
  lows: number[],
  closes: number[],
  volumes: number[],
): number[] {
  const out: number[] = new Array(closes.length).fill(NaN)
  let cumPV = 0
  let cumV = 0
  for (let i = 0; i < closes.length; i++) {
    const typical = (highs[i] + lows[i] + closes[i]) / 3
    cumPV += typical * volumes[i]
    cumV += volumes[i]
    out[i] = cumV > 0 ? cumPV / cumV : NaN
  }
  return out
}

/** MACD(fast, slow, signal): returns the MACD line, signal line, and histogram. */
export function macd(
  values: number[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): { macdLine: number[]; signalLine: number[]; histogram: number[] } {
  const fastE = ema(values, fast)
  const slowE = ema(values, slow)
  const macdLine = values.map((_, i) =>
    Number.isNaN(fastE[i]) || Number.isNaN(slowE[i]) ? NaN : fastE[i] - slowE[i],
  )
  // EMA of the MACD line, seeded once enough MACD values exist.
  const signalLine: number[] = new Array(values.length).fill(NaN)
  const start = slow - 1 // first index with a MACD value
  if (values.length >= start + signalPeriod) {
    let seed = 0
    for (let i = start; i < start + signalPeriod; i++) seed += macdLine[i]
    seed /= signalPeriod
    signalLine[start + signalPeriod - 1] = seed
    const k = 2 / (signalPeriod + 1)
    let prev = seed
    for (let i = start + signalPeriod; i < values.length; i++) {
      prev = macdLine[i] * k + prev * (1 - k)
      signalLine[i] = prev
    }
  }
  const histogram = macdLine.map((m, i) =>
    Number.isNaN(m) || Number.isNaN(signalLine[i]) ? NaN : m - signalLine[i],
  )
  return { macdLine, signalLine, histogram }
}

/** Wilder's RSI. Returns NaN until enough history (i < period). */
export function rsi(values: number[], period = 14): number[] {
  const out: number[] = new Array(values.length).fill(NaN)
  if (values.length <= period) return out

  let gain = 0
  let loss = 0
  for (let i = 1; i <= period; i++) {
    const ch = values[i] - values[i - 1]
    if (ch >= 0) gain += ch
    else loss -= ch
  }
  let avgGain = gain / period
  let avgLoss = loss / period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)

  for (let i = period + 1; i < values.length; i++) {
    const ch = values[i] - values[i - 1]
    const g = ch > 0 ? ch : 0
    const l = ch < 0 ? -ch : 0
    avgGain = (avgGain * (period - 1) + g) / period
    avgLoss = (avgLoss * (period - 1) + l) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}
