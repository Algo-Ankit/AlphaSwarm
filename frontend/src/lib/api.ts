import type {
  AllocationSlice,
  AppNotification,
  BacktestRequest,
  BacktestResult,
  BacktestSummary,
  Bar,
  BillingCurrency,
  CheckoutResponse,
  CreatePostRequest,
  LeaderboardEntry,
  LineageResponse,
  PublishRequest,
  SocialPost,
  SubscribeResponse,
  SubscriptionEntry,
  BrokerConnectRequest,
  BrokerConnection,
  CasHoldingInput,
  Forecast,
  ForecastRequest,
  IndicatorSnapshot,
  LLMConfig,
  LLMConfigCreate,
  NewsItem,
  PortfolioSnapshot,
  PortfolioSummary,
  Strategy,
  StrategyCreateRequest,
  StrategyRunListItem,
  RunOrderDetail,
  StrategyRunResponse,
  Subscription,
  TaskStatusResponse,
  TestConnectionResponse,
  RiskReview,
  TickerSearchResult,
  TokenResponse,
  UnifiedPortfolio,
  UserProfile,
  WealthForecast,
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

/**
 * Single-flight silent refresh. Access tokens expire in 15 minutes; without
 * this every API call after expiry hard-logged the user out even though a
 * perfectly valid refresh token was sitting in storage. All concurrent 401s
 * share ONE refresh request (rotation invalidates the old token, so parallel
 * refreshes would race each other).
 */
let refreshInFlight: Promise<boolean> | null = null

async function trySilentRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const rt = getRefreshToken()
      if (!rt) return false
      try {
        const res = await fetch(`${BASE}/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        })
        if (!res.ok) return false
        const data = (await res.json()) as TokenResponse
        setTokens(data.access_token, data.refresh_token)
        return true
      } catch {
        return false
      }
    })().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

function withFreshAuth(init?: RequestInit): RequestInit {
  const token = getAccessToken()
  return {
    ...init,
    headers: {
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }
}

function forceLogout(): never {
  clearTokens()
  clearUserProfile()
  window.location.href = '/login'
  // Halt the caller — the page is navigating away.
  throw new Error('Session expired')
}

async function req<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined' && !path.includes('/auth/')) {
      if (!retried && (await trySilentRefresh())) {
        return req<T>(path, withFreshAuth(init), true)
      }
      forceLogout()
    }
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

/** Like req() but for 204/empty-body endpoints (DELETE, mark-read, …). */
async function reqVoid(path: string, init?: RequestInit, retried = false): Promise<void> {
  const res = await fetch(`${BASE}${path}`, init)
  if (res.ok || res.status === 204) return
  if (res.status === 401 && typeof window !== 'undefined' && !path.includes('/auth/')) {
    if (!retried && (await trySilentRefresh())) {
      return reqVoid(path, withFreshAuth(init), true)
    }
    forceLogout()
  }
  const text = await res.text().catch(() => res.statusText)
  throw new Error(text || `HTTP ${res.status}`)
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

  forgotPassword: (email: string) =>
    req<{ detail: string }>('/v1/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, newPassword: string) =>
    req<{ detail: string }>('/v1/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  verifyEmail: (token: string) =>
    req<{ detail: string }>('/v1/auth/verify-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }),

  resendVerification: () =>
    req<{ detail: string }>('/v1/auth/resend-verification', {
      method: 'POST',
      headers: authHeaders(),
    }),

  // Broker-identity sign-in: one click authenticates AND connects the brokerage.
  getUpstoxLoginUrl: () =>
    req<{ login_url: string; state: string }>('/v1/auth/broker/upstox/login-url'),

  upstoxLoginCallback: (code: string, state: string) =>
    req<TokenResponse>('/v1/auth/broker/upstox/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
    }),

  // Passwordless OTP login — identifier is an email OR phone number.
  requestOtp: (identifier: string) =>
    req<{ detail: string }>('/v1/auth/otp/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier }),
    }),

  verifyOtp: (identifier: string, code: string) =>
    req<TokenResponse>('/v1/auth/otp/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, code }),
    }),

  // Google sign-in: pure identity, connects no brokerage.
  getGoogleLoginUrl: () =>
    req<{ login_url: string; state: string }>('/v1/auth/google/login-url'),

  googleLoginCallback: (code: string, state: string) =>
    req<TokenResponse>('/v1/auth/google/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
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

  updateStrategyStatus: (id: string, status: 'active' | 'paused' | 'stopped' | 'draft') =>
    req<Strategy>(`/v1/strategies/${id}/status`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    }),

  updateStrategyRisk: (id: string, risk: unknown) =>
    req<Strategy>(`/v1/strategies/${id}/risk`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ risk }),
    }),

  deleteStrategy: (id: string) =>
    req<void>(`/v1/strategies/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    }),

  listRuns: (strategyId?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams()
    if (strategyId) params.set('strategy_id', strategyId)
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    return req<StrategyRunListItem[]>(`/v1/runs?${params.toString()}`, { headers: authHeaders() })
  },

  listRunOrders: (runId: string) =>
    req<RunOrderDetail[]>(`/v1/runs/${runId}/orders`, { headers: authHeaders() }),

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
    reqVoid(`/v1/brokers/${id}`, { method: 'DELETE', headers: authHeaders() }),

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
    reqVoid(`/v1/llm-configs/${id}`, { method: 'DELETE', headers: authHeaders() }),

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
    reqVoid(`/v1/notifications/${id}/read`, { method: 'POST', headers: authHeaders() }),

  markAllNotificationsRead: () =>
    reqVoid('/v1/notifications/read-all', { method: 'POST', headers: authHeaders() }),

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
    reqVoid(`/v1/notifications/${notifId}/approve`, { method: 'POST', headers: authHeaders() }),

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

  // ── AI Investment Advisor (BYOK) ──────────────────────────────
  analyzeAdvisor: (query: string) =>
    req<{ response: string }>('/v1/ai-advisor/analyze', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ query }),
    }),

  // ── Social copy trading ───────────────────────────────────────
  getLeaderboard: (limit = 50) =>
    req<LeaderboardEntry[]>(`/v1/social/leaderboard?limit=${limit}`, {
      headers: authHeaders(),
    }),

  publishStrategy: (data: PublishRequest) =>
    req<{ public_strategy_id: string; strategy_id: string; title: string; subscriber_count: number }>(
      '/v1/social/publish',
      { method: 'POST', headers: authHeaders(), body: JSON.stringify(data) },
    ),

  forkStrategy: (publicStrategyId: string) =>
    req<{ strategy_id: string; name: string; forked_from_public_strategy_id: string }>(
      `/v1/social/fork/${publicStrategyId}`,
      { method: 'POST', headers: authHeaders() },
    ),

  getLineage: (publicStrategyId: string) =>
    req<LineageResponse>(`/v1/social/lineage/${publicStrategyId}`, { headers: authHeaders() }),

  subscribeStrategy: (publicStrategyId: string, allocatedCapital: number) =>
    req<SubscribeResponse>(`/v1/social/subscribe/${publicStrategyId}`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ allocated_capital: allocatedCapital }),
    }),

  unsubscribeStrategy: (publicStrategyId: string) =>
    reqVoid(`/v1/social/subscribe/${publicStrategyId}`, {
      method: 'DELETE',
      headers: authHeaders(),
    }),

  listSubscriptions: () =>
    req<SubscriptionEntry[]>('/v1/social/subscriptions', { headers: authHeaders() }),

  // ── Social Feed ───────────────────────────────────────────────────────────────
  getFeedTimeline: (opts: { limit?: number; offset?: number } = {}) => {
    const qs = new URLSearchParams({
      limit: String(opts.limit ?? 50),
      offset: String(opts.offset ?? 0),
    })
    return req<SocialPost[]>(`/v1/feed/timeline?${qs}`, { headers: authHeaders() })
  },

  createPost: (data: CreatePostRequest) =>
    req<SocialPost>('/v1/feed/post', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  togglePostLike: (postId: string) =>
    req<{ post_id: string; liked: boolean; likes_count: number }>(
      `/v1/feed/${postId}/like`,
      { method: 'POST', headers: authHeaders() },
    ),

  // ── Unified Portfolio (multi-broker CAS) ──────────────────────
  getUnifiedPortfolio: () =>
    req<UnifiedPortfolio>('/v1/portfolio/unified', { headers: authHeaders() }),

  uploadCas: (data: { statement_date?: string | null; holdings: CasHoldingInput[] }) =>
    req<UnifiedPortfolio>('/v1/portfolio/upload-cas', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),

  // Real-time holdings risk review (deterministic; set includeAi for a narrative)
  getRiskReview: (includeAi = false) =>
    req<RiskReview>(`/v1/portfolio/risk-review?include_ai=${includeAi}`, {
      headers: authHeaders(),
    }),

  // ── Monte Carlo wealth forecast ───────────────────────────────
  forecastWealth: (data: ForecastRequest) =>
    req<WealthForecast>('/v1/portfolio/forecast', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }),
}
