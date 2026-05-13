export type TrendType = 'strong_up' | 'up' | 'neutral' | 'down' | 'strong_down'

export interface StockInput {
  stock_input: string
  position_status: '已持有' | '未持有'
  cost_price?: number | null
}

export interface WatchlistItem {
  stock_code: string
  stock_name: string
  position_status: '已持有' | '未持有'
  cost_price?: number | null
  added_at?: string
  cached_signal?: string
  cached_signal_score?: number
  cached_signal_time?: string
}

export interface AnalysisRequest {
  stock_input: string
  position_status: '已持有' | '未持有'
  cost_price?: number | null
}

export interface TradingSignal {
  score: number
  signal: string
  signal_text: string
  reason?: string
}

export interface PricePredictionDay {
  target_low: number | null
  target_high: number | null
  trend: TrendType
  signal: string
}

export interface PricePrediction {
  current: number | null
  support: number | null
  resistance: number | null
  day1: PricePredictionDay
  day2: PricePredictionDay
  validation_confidence?: number | null
  validation_note?: string
}

export interface AnalysisValidation {
  direction_consensus: string
  confidence: number
  risk_level: string
  action_gate: string
  supporting_factors: string[]
  opposing_factors: string[]
  conflicts: string[]
  validation_note: string
  weighted_bullish?: number
  weighted_bearish?: number
  active_weight_total?: number
  missing_dimensions?: string[]
  signal_persistence?: Record<string, { direction: string; days: number }>
}

export interface PositionStrategyHeld {
  avg_cost: number
  current_price: number
  price_change_pct: number
  stop_profit_price: number
  stop_profit_pct: number
  stop_loss_price: number
  stop_loss_pct: number
  position_adjust: string
  reason: string
}

export interface PositionStrategyNotHeld {
  current_price: number
  buy_timing: string
  position_size_pct: number
  stop_loss_price: number
  risk_level: string
  risk_control: string
}

export interface KlineData {
  dates: string[]
  opens: number[]
  closes: number[]
  highs: number[]
  lows: number[]
  volumes: number[]
  ma5: number[]
  ma10: number[]
  ma20: number[]
  ma60: number[]
  boll_upper: number[]
  boll_middle: number[]
  boll_lower: number[]
}

export interface TechnicalChartData {
  dates: string[]
  macd: number[]
  dif: number[]
  dea: number[]
  rsi6: number[]
  rsi12: number[]
  k: number[]
  d: number[]
  j: number[]
}

export interface FundFlowData {
  dates: string[]
  main_flow: number[]
  main_flow_ratio: number[]
  small_flow: number[]
  change_pct: number[]
}

export interface AnalysisResult {
  stock_code: string
  stock_name: string
  analysis: {
    technical_score: number
    fund_flow_score: number
    sentiment_score: number
    overall_score: number
    recommendation: string
    details: Record<string, any>
  }
  trading_signal: TradingSignal
  price_prediction: PricePrediction
  validation?: AnalysisValidation
  indicators: Record<string, any>
  position_strategy: PositionStrategyHeld | PositionStrategyNotHeld | Record<string, any>
  stock_info: Record<string, any>
  charts: {
    kline: KlineData
    technical: TechnicalChartData
    fund_flow: FundFlowData
  }
}

export interface BacktestRequest {
  stock_code: string
  mode: 'builtin' | 'custom'
  params?: {
    atr_multiplier?: number
    lookback_days?: number
  }
  algorithm_code?: string
  algorithm_name?: string
}

export interface BacktestResult {
  stock_code: string
  effective_params?: {
    atr_multiplier: number
    lookback_days: number
  }
  statistics: {
    day1_accuracy: number
    day2_accuracy: number
    day1_trend_accuracy: number
    day2_trend_accuracy: number
    sharpe_ratio: number
    max_drawdown: number
    total_predictions?: number
    mean_width_pct?: number
    median_width_pct?: number
    midpoint_mae_pct?: number
    coverage_width_score?: number
    total_return?: number
    total_cost?: number
    turnover?: number
    trades?: number
    win_rate?: number
  }
  predictions: Array<{
    date: string
    trend: TrendType
    predicted_low: number
    predicted_high: number
    actual_price: number | null
    current_price: number | null
    hit: boolean
  }>
  equity_curve: Array<{
    date: string
    value: number
    position?: number
    daily_return?: number
    turnover?: number
    cost?: number
  }>
}

export interface BatchAnalysisRequest {
  stocks: AnalysisRequest[]
}

export interface BatchAnalysisResult {
  results: AnalysisResult[]
  errors: Array<{ stock_input: string; error: string }>
}

export interface ProgressMessage {
  type: 'progress'
  task_id: string
  current: number
  total: number
  current_stock: string
  status: 'analyzing' | 'completed' | 'error'
}
