import type {
  BacktestRequest,
  BacktestResult,
  BacktestSummary,
  BrokerConnectRequest,
  BrokerConnection,
  LLMConfig,
  LLMConfigCreate,
  Strategy,
  StrategyCreateRequest,
  StrategyRunResponse,
  TaskStatusResponse,
  TestConnectionResponse,
  TickerSearchResult,
  TokenResponse,
  UserProfile,
} from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

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
}
