/**
 * Client-side market-session status, mirroring app/domain/market_hours.py.
 * Used for the "market hours status badge throughout" Phase 6 requirement.
 * This is a display convenience; the backend remains the source of truth for
 * the actual trading gate (risk.py / MarketState).
 */

export type SessionStatus = 'pre_market' | 'open' | 'after_hours' | 'closed'

interface Schedule {
  tz: string
  open: number          // minutes-from-midnight, local exchange time
  close: number
  preOpen: number
  afterClose: number
  weekdays: number[]    // JS getDay(): 0=Sun … 6=Sat
}

const hm = (h: number, m: number) => h * 60 + m
const WEEKDAYS = [1, 2, 3, 4, 5]          // Mon–Fri
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]

const SCHEDULES: Record<string, Schedule> = {
  NASDAQ: { tz: 'America/New_York', open: hm(9, 30), close: hm(16, 0), preOpen: hm(4, 0), afterClose: hm(20, 0), weekdays: WEEKDAYS },
  NYSE:   { tz: 'America/New_York', open: hm(9, 30), close: hm(16, 0), preOpen: hm(4, 0), afterClose: hm(20, 0), weekdays: WEEKDAYS },
  NSE:    { tz: 'Asia/Kolkata',     open: hm(9, 15), close: hm(15, 30), preOpen: hm(9, 0), afterClose: hm(15, 30), weekdays: WEEKDAYS },
  BSE:    { tz: 'Asia/Kolkata',     open: hm(9, 15), close: hm(15, 30), preOpen: hm(9, 0), afterClose: hm(15, 30), weekdays: WEEKDAYS },
  CRYPTO: { tz: 'UTC',             open: hm(0, 0),  close: hm(23, 59), preOpen: hm(0, 0), afterClose: hm(23, 59), weekdays: ALL_DAYS },
}

/** Local weekday + minutes-from-midnight for a given IANA timezone. */
function localParts(tz: string, now: Date): { weekday: number; minutes: number } {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  })
  const parts = fmt.formatToParts(now)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const days: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }
  let hour = parseInt(get('hour'), 10)
  if (hour === 24) hour = 0 // some engines emit "24" at midnight
  return { weekday: days[get('weekday')] ?? 0, minutes: hm(hour, parseInt(get('minute'), 10)) }
}

export function sessionStatus(exchange: string, now: Date = new Date()): SessionStatus {
  const s = SCHEDULES[exchange.toUpperCase()]
  if (!s) return 'closed'
  const { weekday, minutes } = localParts(s.tz, now)
  if (!s.weekdays.includes(weekday)) return 'closed'
  if (minutes >= s.open && minutes < s.close) return 'open'
  if (minutes >= s.preOpen && minutes < s.open) return 'pre_market'
  if (minutes >= s.close && minutes <= s.afterClose) return 'after_hours'
  return 'closed'
}

export const SESSION_LABEL: Record<SessionStatus, string> = {
  pre_market: 'Pre-Market',
  open: 'Market Open',
  after_hours: 'After Hours',
  closed: 'Market Closed',
}

export const SESSION_VARIANT: Record<SessionStatus, 'success' | 'warning' | 'muted'> = {
  open: 'success',
  pre_market: 'warning',
  after_hours: 'warning',
  closed: 'muted',
}
