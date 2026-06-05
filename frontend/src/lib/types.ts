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

export interface BacktestRequest {
  symbol: string
  exchange?: string
  timeframe?: string
  limit?: number
  initial_equity?: number
}

export interface BacktestResult {
  strategy_id: string
  symbol: string
  timeframe: string
  bars_processed: number
  trades: BacktestTrade[]
  equity_curve: number[]
  metrics: BacktestMetrics
  started_at: string
  completed_at: string
}
