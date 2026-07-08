export type StrategyStatus = 'draft' | 'active' | 'paused' | 'archived'
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'rejected'

export interface StrategyRiskConfig {
  max_order_notional: number
  max_position_notional: number
  max_open_positions: number
  max_daily_notional: number
  stop_loss_pct: number | null
  take_profit_pct: number | null
  slippage_bps: number
  commission_per_share: number
  trade_session: string
  allowed_symbols: string[]
  paper_trading_only: boolean
}

export interface TickerSearchResult {
  symbol: string
  name: string
  exchange: string
}

export interface Strategy {
  id: string
  tenant_id: string
  owner_user_id: string
  name: string
  prompt: string
  symbols: string[]
  exchange: string
  timeframe: string
  status: StrategyStatus
  generated_logic: string
  explanation: string
  risk: StrategyRiskConfig
  sip_paused: boolean
  sip_monthly_amount: number | null
  sip_frequency: string
  created_at: string
  updated_at: string
}

export interface StrategyCreateRequest {
  name: string
  prompt: string
  symbols: string[]
  exchange?: string
  timeframe: string
  risk?: Partial<StrategyRiskConfig>
  creation_mode?: 'nl' | 'quant'
  code_source?: string
}

export interface StrategyRunResponse {
  run_id: string
  strategy_id: string
  task_id: string
  status: RunStatus
  dry_run: boolean
  message: string
}

export interface TaskStatusResponse {
  task_id: string
  celery_status: string
  result: Record<string, unknown> | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user_id: string
  tenant_id: string
  email: string
  role: string
  display_name: string
  tenant_name: string
  plan: string
  email_verified: boolean
}

export interface UserProfile {
  display_name: string
  tenant_name: string
  plan: string
  email: string
}

export type OAuthTokenStatus = 'connected' | 'expired' | 'none'

export interface BrokerConnection {
  id: string
  broker: string
  base_url: string | null
  is_paper: boolean
  is_active: boolean
  key_preview: string
  oauth_connected: boolean
  token_status: OAuthTokenStatus
  token_expires_at: string | null
  created_at: string
  updated_at: string
}

export interface BrokerConnectRequest {
  broker: string
  api_key: string
  api_secret: string
  is_paper: boolean
  base_url?: string
}

export interface TestConnectionResponse {
  ok: boolean
  message: string
  account_id: string | null
}

// ── LLM Configs (BYOAK) ───────────────────────────────────────────────────

export interface LLMConfig {
  id:          string
  label:       string
  provider:    'groq' | 'gemini' | 'openrouter' | 'openai' | 'together' | 'anthropic' | 'custom'
  base_url:    string
  model:       string
  key_preview: string
  created_at:  string
}

export interface LLMConfigCreate {
  label:    string
  provider: LLMConfig['provider']
  base_url: string
  api_key:  string
  model:    string
}

// ── Phase 5: Backtesting ───────────────────────────────────────────────────

export interface BacktestMetrics {
  total_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  total_trades: number
  profitable_trades: number
  initial_equity: number
  final_equity: number
  // Phase 5 extended metrics
  sortino_ratio: number
  cagr_pct: number
  calmar_ratio: number
  profit_factor: number
  benchmark_return_pct: number
  alpha_vs_benchmark_pct: number
}

export interface BacktestTrade {
  bar_index: number
  timestamp: string
  symbol: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
}

export interface BacktestBar {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface BacktestRequest {
  symbol: string
  exchange?: string
  timeframe?: string
  limit?: number
  initial_equity?: number
  start_date?: string
  end_date?: string
}

export interface BacktestResult {
  strategy_id: string
  symbol: string
  timeframe: string
  bars_processed: number
  bars: BacktestBar[]
  trades: BacktestTrade[]
  equity_curve: number[]
  metrics: BacktestMetrics
  started_at: string
  completed_at: string
}

export interface BacktestSummary {
  ran_at: string
  symbol: string
  exchange: string
  timeframe: string
  total_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  total_trades: number
  cagr_pct?: number
  sortino_ratio?: number
  calmar_ratio?: number
  profit_factor?: number
}

// ── Unified portfolio (multi-broker CAS ingestion) ─────────────────────────────

export interface UnifiedHolding {
  isin: string | null
  symbol: string
  name: string
  asset_class: string
  broker: string
  quantity: number
  avg_cost: number
  current_price: number | null
  current_value: number
}

export interface UnifiedPortfolio {
  statement_date: string | null
  holdings_count: number
  total_value: number
  total_cost: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  by_broker: Record<string, number>
  by_asset_class: Record<string, number>
  holdings: UnifiedHolding[]
}

export interface CasHoldingInput {
  symbol: string
  name?: string
  isin?: string | null
  asset_class?: string
  broker?: string
  quantity: number
  avg_cost?: number
  current_price?: number | null
}

// ── Monte Carlo wealth forecast ────────────────────────────────────────────────

export interface ForecastYearProjection {
  year: number
  contributed: number
  pessimistic: number
  median: number
  optimistic: number
}

export interface WealthForecast {
  current_portfolio_value: number
  monthly_contribution: number
  expected_cagr: number
  annual_volatility: number
  years: number
  simulations: number
  total_contributed: number
  projections: ForecastYearProjection[]
  disclaimer: string
}

export interface ForecastRequest {
  current_portfolio_value: number
  monthly_contribution: number
  expected_cagr: number
  annual_volatility: number
  years_to_forecast: number
  simulations?: number
}

// ── Phase 6: Trading Terminal ──────────────────────────────────────────────

export interface Bar {
  symbol: string
  exchange: string
  timeframe: string
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/** Live bar pushed over the WS bars channel. */
export interface BarTick extends Bar {
  type: 'bar'
}

/**
 * Indicator snapshot. `indicators` keys are the requested specs
 * (e.g. "rsi_14", "macd_12_26_9", "ema_50"); values are the latest float
 * or null when not enough history.
 */
export interface IndicatorSnapshot {
  symbol: string
  exchange: string
  timeframe: string
  timestamp: string
  close: number
  indicators: Record<string, number | null>
}

export interface ForecastPoint {
  date: string
  yhat: number
  yhat_lower: number
  yhat_upper: number
}

export interface Forecast {
  symbol: string
  exchange: string
  generated_at: string
  horizon_days: number
  model: string
  mae: number | null
  mape: number | null
  forecast: ForecastPoint[]
  disclaimer: string
}

export type NewsSentiment = 'positive' | 'negative' | 'neutral'

export interface NewsItem {
  symbol: string
  headline: string
  summary: string
  source: string
  url: string
  sentiment: NewsSentiment
  category: string
  published_at: string
}

// ── Phase 6: Portfolio + Notifications ─────────────────────────────────────

export interface PortfolioSummary {
  snapshot_time: string | null
  total_equity: number
  open_pnl: number
  realized_pnl_today: number
  active_strategies: number
  has_data: boolean
}

export interface PortfolioSnapshot {
  snapshot_time: string
  total_equity: number
  open_pnl: number
  realized_pnl_today: number
  active_strategies: number
}

/** Live portfolio update pushed over /v1/ws/portfolio. */
export interface PortfolioTick extends PortfolioSnapshot {
  type: 'portfolio'
}

// ── Portfolio Allocation ───────────────────────────────────────────────────────

export interface AllocationSlice {
  label: string
  value: number
  pct: number
  color: string
}

// ── Notification types ─────────────────────────────────────────────────────────

export type NotificationType =
  | 'trade_executed' | 'bot_error' | 'pnl_threshold' | 'news' | 'system' | 'rebalance_approval'

export interface AppNotification {
  id: string
  type: NotificationType
  title: string
  body: string
  entity_type: string | null
  entity_id: string | null
  is_read: boolean
  approved_at: string | null
  created_at: string
}

/** Live notification pushed over /v1/ws/portfolio. */
export interface NotificationTick {
  type: 'notification'
  ts: string
  notification: AppNotification
}

export type PortfolioWsMessage = PortfolioTick | NotificationTick | { type: 'pong' }

// ── Social copy trading ────────────────────────────────────────────────────────

export interface LeaderboardEntry {
  public_strategy_id: string
  strategy_id: string
  title: string
  description: string
  creator_name: string
  symbols: string[]
  exchange: string
  management_fee_bps: number
  subscriber_count: number
  fork_count: number
  forked_from_public_strategy_id: string | null
  is_verified: boolean
  cagr_pct: number | null
  total_return_pct: number | null
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
  win_rate_pct: number | null
  total_trades: number | null
  oos_cagr_pct: number | null
  oos_total_return_pct: number | null
  oos_sharpe_ratio: number | null
  oos_max_drawdown_pct: number | null
  oos_total_trades: number | null
  oos_computed: boolean
}

export interface LineageNode {
  public_strategy_id: string
  title: string
}

export interface LineageChild {
  public_strategy_id: string
  title: string
  creator_name: string
  subscriber_count: number
  fork_count: number
  sharpe_ratio: number | null
  cagr_pct: number | null
}

export interface LineageResponse {
  ancestors: LineageNode[]
  children: LineageChild[]
}

export interface PublishRequest {
  strategy_id: string
  title: string
  description?: string
  management_fee_bps?: number
}

export interface SubscribeResponse {
  subscription_id: string
  public_strategy_id: string
  allocated_capital: number
  is_active: boolean
}

export interface SubscriptionEntry {
  subscription_id: string
  public_strategy_id: string
  strategy_id: string
  title: string
  allocated_capital: number
  management_fee_bps: number
  subscriber_count: number
}

// ── Social Feed ────────────────────────────────────────────────────────────────

export interface SocialPost {
  id: string
  author_tenant_id: string
  author_name: string
  public_strategy_id: string | null
  strategy_title: string | null
  cagr_pct: number | null
  sharpe_ratio: number | null
  content_markdown: string
  likes_count: number
  created_at: string
  is_subscribed: boolean
  liked_by_me: boolean
}

export interface CreatePostRequest {
  content_markdown: string
  public_strategy_id?: string | null
}

// ── Billing (dual gateway) ─────────────────────────────────────────────────────

/** Currency the user pays in — selects the gateway (USD→Stripe, INR→Razorpay). */
export type BillingCurrency = 'USD' | 'INR'

export interface CheckoutResponse {
  gateway: 'stripe' | 'razorpay'
  /** URL to redirect to (Stripe Checkout page or Razorpay hosted authorization). */
  checkout_url: string
  reference_id: string
}

export interface Subscription {
  plan: string
  subscription_status: string
  is_active: boolean
  current_period_end: string | null
}
