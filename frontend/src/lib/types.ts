export type StrategyStatus = 'draft' | 'active' | 'paused' | 'archived'
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'rejected'

export interface StrategyRiskConfig {
  max_order_notional: number
  max_daily_notional: number
  allowed_symbols: string[]
  paper_trading_only: boolean
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
