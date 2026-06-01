export const TIMEFRAMES = [
  { value: '1Min',  label: '1 Minute' },
  { value: '5Min',  label: '5 Minutes' },
  { value: '15Min', label: '15 Minutes' },
  { value: '1Hour', label: '1 Hour' },
  { value: '1Day',  label: '1 Day' },
]

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
