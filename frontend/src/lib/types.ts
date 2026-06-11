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
  risk: StrategyRiskConfig
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
}

export interface UserProfile {
  display_name: string
  tenant_name: string
  plan: string
  email: string
}

export interface BrokerConnection {
  id: string
  broker: string
  base_url: string | null
  is_paper: boolean
  is_active: boolean
  key_preview: string
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
  provider:    'groq' | 'openai' | 'together' | 'anthropic' | 'custom'
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
}
