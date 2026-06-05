// Values must match market_data.py _alpaca_timeframe / _YF_PARAMS keys exactly.
export const TIMEFRAMES = [
  { value: '1m',  label: '1 min' },
  { value: '5m',  label: '5 min' },
  { value: '15m', label: '15 min' },
  { value: '1h',  label: '1 hour' },
  { value: '4h',  label: '4 hour' },
  { value: '1d',  label: '1 day' },
  { value: '1w',  label: '1 week' },
]

// Normalise legacy timeframe values saved before the constants fix.
export const TIMEFRAME_NORMALIZE: Record<string, string> = {
  '1Min':  '1m',
  '5Min':  '5m',
  '15Min': '15m',
  '1Hour': '1h',
  '4Hour': '4h',
  '1Day':  '1d',
}

export function normalizeTimeframe(tf: string): string {
  return TIMEFRAME_NORMALIZE[tf] ?? tf
}

export const DEFAULT_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'QQQ', 'SPY', 'TSLA']

export const STATUS_BADGE = {
  draft:    'default',
  active:   'success',
  paused:   'warning',
  archived: 'muted',
} as const

export const RUN_BADGE = {
  queued:    'warning',
  running:   'info',
  completed: 'success',
  failed:    'danger',
  rejected:  'danger',
  success:   'success',
  failure:   'danger',
  pending:   'warning',
  started:   'info',
} as const
