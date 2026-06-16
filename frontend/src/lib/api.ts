import type {
  AllocationSlice,
  AppNotification,
  BacktestRequest,
  BacktestResult,
  BacktestSummary,
  Bar,
  BillingCurrency,
  CheckoutResponse,
  BrokerConnectRequest,
  BrokerConnection,
  Forecast,
  IndicatorSnapshot,
  LLMConfig,
  LLMConfigCreate,
  NewsItem,
  PortfolioSnapshot,
  PortfolioSummary,
  Strategy,
  StrategyCreateRequest,
  StrategyRunResponse,
  Subscription,
  TaskStatusResponse,
  TestConnectionResponse,
  TickerSearchResult,
  TokenResponse,
  UserProfile,
} from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/** WS base derived from the HTTP base (http→ws, https→wss). */
export function wsBase(): string {
  return BASE.replace(/^http/, 'ws')
}

/**
 * URL for the live-bars WebSocket channel. JWT is passed as ?token= because
 * browsers can't set headers on a WebSocket handshake (matches app/api/ws.py).
 */
export function barsSocketUrl(
  symbol: string,
  exchange: string,
  timeframe: string,
): string {
  const token = getAccessToken() ?? ''
  const qs = new URLSearchParams({ exchange, timeframe, token })
  return `${wsBase()}/v1/ws/bars/${encodeURIComponent(symbol.toUpperCase())}?${qs}`
}

/** URL for the portfolio WS channel (live P&L snapshots + notifications). */
export function portfolioSocketUrl(): string {
  const token = getAccessToken() ?? ''
  return `${wsBase()}/v1/ws/portfolio?${new URLSearchParams({ token })}`
}

const ACCESS_KEY  = 'alphaswarm_access_token'
const REFRESH_KEY = 'alphaswarm_refresh_token'
const PROFILE_KEY = 'alphaswarm_user_profile'

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function getUserProfile(): UserProfile | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(PROFILE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserProfile
  } catch {
    return null
  }
}

export function setUserProfile(profile: UserProfile): void {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
}

export function clearUserProfile(): void {
  localStorage.removeItem(PROFILE_KEY)
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined' && !path.includes('/auth/')) {
      clearTokens()
      clearUserProfile()
      window.location.href = '/login'
      return new Promise(() => {})
    }
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  // ── Auth ──────────────────────────────────────────────────
  register: (data: {
    email: string
    password: string
    display_name: string
    tenant_name: string
  }) =>
    req<TokenResponse>('/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  login: (email: string, password: string) =>
    req<TokenResponse>('/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }),

  refreshToken: (refreshToken: string) =>
    req<TokenResponse>('/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),

  logout: (refreshToken: string) =>
    req<void>('/v1/auth/logout', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),

  // ── Strategies ────────────────────────────────────────────
  listStrategies: () =>
    req<Strategy[]>('/v1/strategies', { headers: authHeaders() }),

  getStrategy: (id: string) =>
    req<Strategy>(`/v1/strategies/${id}`, { headers: authHeaders() }),

  createStrategy: (data: StrategyCreateRequest) =>
    req<Strategy>('/v1/strategies', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  updateStrategyCode: (id: string, code_source: string) =>
    req<Strategy>(`/v1/strategies/${id}/code`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ code_source }),
    }),

  runStrategy: (id: string, dryRun = true) =>
    req<StrategyRunResponse>(`/v1/strategies/${id}/runs`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ dry_run: dryRun }),
    }),

  getTaskStatus: (taskId: string) =>
    req<TaskStatusResponse>(`/v1/tasks/${taskId}`, { headers: authHeaders() }),

  // ── Brokers ───────────────────────────────────────────────
  listBrokers: () =>
    req<BrokerConnection[]>('/v1/brokers', { headers: authHeaders() }),

  connectBroker: (data: BrokerConnectRequest) =>
    req<BrokerConnection>('/v1/brokers', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  deleteBroker: (id: string) =>
    fetch(`${BASE}/v1/brokers/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    }).then((r) => {
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`)
    }),

  testBroker: (id: string) =>
    req<TestConnectionResponse>(`/v1/brokers/${id}/test`, {
      method: 'PATCH',
      headers: authHeaders(),
    }),

  // ── LLM Configs (BYOAK) ──────────────────────────────────
  listLLMConfigs: () =>
    req<LLMConfig[]>('/v1/llm-configs', { headers: authHeaders() }),

  addLLMConfig: (data: LLMConfigCreate) =>
    req<LLMConfig>('/v1/llm-configs', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  deleteLLMConfig: (id: string) =>
    fetch(`${BASE}/v1/llm-configs/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    }).then((r) => {
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`)
    }),

  // ── Search ────────────────────────────────────────────────
  searchTickers: (q: string, limit = 8) =>
    req<TickerSearchResult[]>(
      `/v1/market/search?q=${encodeURIComponent(q)}&limit=${limit}`,
      { headers: authHeaders() },
    ),

  // ── Market data (Phase 6) ─────────────────────────────────
  getBars: (
    symbol: string,
    opts: { exchange?: string; timeframe?: string; limit?: number; start?: string; end?: string } = {},
  ) => {
    const qs = new URLSearchParams({
      exchange: opts.exchange ?? 'NASDAQ',
      timeframe: opts.timeframe ?? '1d',
      limit: String(opts.limit ?? 500),
      ...(opts.start ? { start: opts.start } : {}),
      ...(opts.end ? { end: opts.end } : {}),
    })
    return req<Bar[]>(`/v1/market/bars/${encodeURIComponent(symbol)}?${qs}`, {
      headers: authHeaders(),
    })
  },

  getIndicators: (
    symbol: string,
    opts: { exchange?: string; timeframe?: string; indicators?: string } = {},
  ) => {
    const qs = new URLSearchParams({
      exchange: opts.exchange ?? 'NASDAQ',
      timeframe: opts.timeframe ?? '1d',
      ...(opts.indicators ? { indicators: opts.indicators } : {}),
    })
    return req<IndicatorSnapshot>(
      `/v1/market/indicators/${encodeURIComponent(symbol)}?${qs}`,
      { headers: authHeaders() },
    )
  },

  getForecast: (
    symbol: string,
    opts: { exchange?: string; horizon?: number } = {},
  ) => {
    const qs = new URLSearchParams({
      exchange: opts.exchange ?? 'NASDAQ',
      horizon: String(opts.horizon ?? 5),
    })
    return req<Forecast>(`/v1/market/forecast/${encodeURIComponent(symbol)}?${qs}`, {
      headers: authHeaders(),
    })
  },

  getNews: (
    symbol: string,
    opts: { exchange?: string; days?: number; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams({
      exchange: opts.exchange ?? 'NASDAQ',
      days: String(opts.days ?? 7),
      limit: String(opts.limit ?? 20),
    })
    return req<NewsItem[]>(`/v1/market/news/${encodeURIComponent(symbol)}?${qs}`, {
      headers: authHeaders(),
    })
  },

  // ── Portfolio (Phase 6) ───────────────────────────────────
  getPortfolioSummary: () =>
    req<PortfolioSummary>('/v1/portfolio/summary', { headers: authHeaders() }),

  getPortfolioSnapshots: (limit = 200) =>
    req<PortfolioSnapshot[]>(`/v1/portfolio/snapshots?limit=${limit}`, {
      headers: authHeaders(),
    }),

  // ── Notifications (Phase 6) ───────────────────────────────
  listNotifications: (opts: { unreadOnly?: boolean; limit?: number } = {}) => {
    const qs = new URLSearchParams({
      unread_only: String(opts.unreadOnly ?? false),
      limit: String(opts.limit ?? 50),
    })
    return req<AppNotification[]>(`/v1/notifications?${qs}`, { headers: authHeaders() })
  },

  unreadNotificationCount: () =>
    req<{ count: number }>('/v1/notifications/unread-count', { headers: authHeaders() }),

  markNotificationRead: (id: string) =>
    fetch(`${BASE}/v1/notifications/${id}/read`, { method: 'POST', headers: authHeaders() })
      .then((r) => { if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`) }),

  markAllNotificationsRead: () =>
    fetch(`${BASE}/v1/notifications/read-all`, { method: 'POST', headers: authHeaders() })
      .then((r) => { if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`) }),

  // ── Broker OAuth ──────────────────────────────────────────────
  getBrokerOAuthLoginUrl: (broker: string) =>
    req<{ login_url: string; state: string | null }>(`/v1/brokers/oauth/${broker}/login-url`, {
      headers: authHeaders(),
    }),

  exchangeBrokerOAuthCode: (body: { broker: string; code?: string; request_token?: string; state?: string }) =>
    req<BrokerConnection>('/v1/brokers/oauth/callback', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    }),

  angeloneLogin: (data: { client_id: string; password: string; totp: string }) =>
    req<BrokerConnection>('/v1/brokers/oauth/angelone/login', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  // ── Market hours ──────────────────────────────────────────────
  getMarketHours: (exchange: string) =>
    req<{ exchange: string; status: string; next_open: string | null; timezone: string }>(
      `/v1/market/hours/${encodeURIComponent(exchange)}`,
      { headers: authHeaders() },
    ),

  // ── Portfolio allocation ──────────────────────────────────────
  getPortfolioAllocation: () =>
    req<AllocationSlice[]>('/v1/portfolio/allocation', { headers: authHeaders() }),

  // ── SIP controls ──────────────────────────────────────────────
  updateSip: (strategyId: string, paused: boolean) =>
    req<Strategy>(`/v1/strategies/${strategyId}/sip`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ paused }),
    }),

  lumpSumBoost: (strategyId: string, amount: number) =>
    req<{ notification_id: string; status: string }>(`/v1/strategies/${strategyId}/lump-sum`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ amount }),
    }),

  // ── Rebalance approval ────────────────────────────────────────
  approveRebalance: (notifId: string) =>
    fetch(`${BASE}/v1/notifications/${notifId}/approve`, {
      method: 'POST',
      headers: authHeaders(),
    }).then((r) => { if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`) }),

  // ── Backtest ──────────────────────────────────────────────
  runBacktest: (strategyId: string, params: BacktestRequest) =>
    req<BacktestResult>(`/v1/strategies/${strategyId}/backtest`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(params),
    }),

  getLatestBacktest: (strategyId: string) =>
    req<BacktestSummary>(`/v1/strategies/${strategyId}/backtests/latest`, {
      headers: authHeaders(),
    }),

  // ── Billing (dual gateway) ────────────────────────────────────
  // Currency routes the gateway: USD → Stripe (Global), INR → Razorpay (India).
  createCheckout: (currency: BillingCurrency) =>
    req<CheckoutResponse>('/v1/billing/checkout', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ currency }),
    }),

  getSubscription: () =>
    req<Subscription>('/v1/billing/subscription', { headers: authHeaders() }),
}
