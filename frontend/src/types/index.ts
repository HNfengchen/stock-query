export type AnalysisStage = 'stage_basic' | 'stage_technical' | 'stage_risk' | 'stage_prediction' | 'stage_complete'

export interface LogEntry {
  timestamp: string
  level: 'INFO' | 'WARN' | 'ERROR'
  message: string
}

export interface StageResult {
  stage: AnalysisStage
  data: Partial<AnalysisResult>
  timestamp: number
}

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
  cost_price?: number | undefined
}

export interface TradingSignal {
  score: number
  signal: string
  signal_text: string
  reason?: string
  action_gate?: string
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
  hybrid_alpha?: number | null
  ml_prediction?: MlPrediction | null
}

export interface AnalysisValidation {
  direction_consensus: string
  confidence: number
  risk_level: string
  action_gate: string
  supporting_factors: string[] | null
  opposing_factors: string[] | null
  conflicts: string[] | null
  validation_note: string
  weighted_bullish?: number
  weighted_bearish?: number
  active_weight_total?: number
  missing_dimensions?: string[]
  signal_persistence?: Record<string, { direction: string; days: number }>
  stress_test?: StressTestResult
}

export interface StressTestResult {
  signal_flip_rate: number | null
  is_robust: boolean | null
  risk_metrics: {
    max_drawdown: number | null
    sharpe: number | null
    sortino: number | null
    calmar: number | null
  } | null
  original_signal: string
  simulation_count: number
  status?: string
}

export interface PositionStrategyHeld {
  avg_cost?: number | null
  current_price?: number | null
  price_change_pct?: number | null
  stop_profit_price?: number | null
  stop_profit_pct?: number | null
  stop_loss_price?: number | null
  stop_loss_pct?: number | null
  position_adjust?: string
  reason?: string
}

export interface PositionStrategyNotHeld {
  current_price?: number | null
  buy_timing?: string
  position_size_pct?: number | null
  stop_loss_price?: number | null
  risk_level?: string
  risk_control?: string
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

export interface IndicatorLatest {
  DIF?: number
  DEA?: number
  bandwidth?: number
  K?: number
  D?: number
  J?: number
  [key: string]: unknown
}

export interface IndicatorEntry {
  signal?: string
  latest?: IndicatorLatest
  [key: string]: unknown
}

export interface RSIEntry {
  signal?: string
  latest?: number
  [key: string]: unknown
}

export interface DistributionWindow {
  var_95?: { latest?: number | null; signal?: string }
  var_99?: { latest?: number | null; signal?: string }
  cvar_95?: { latest?: number | null }
  cvar_99?: { latest?: number | null }
  kurtosis?: { latest?: number | null; signal?: string }
  [key: string]: unknown
}

export interface DistributionIndicators {
  W20?: DistributionWindow
  W60?: DistributionWindow
  [key: string]: unknown
}

export interface Indicators {
  MACD?: IndicatorEntry
  RSI?: Record<string, RSIEntry>
  KDJ?: IndicatorEntry
  BOLL?: { latest?: { bandwidth: number; [key: string]: unknown }; signal?: string; [key: string]: unknown }
  Distribution?: DistributionIndicators
  [key: string]: unknown
}

export interface StockInfo {
  '涨跌幅'?: number
  '涨跌额'?: number
  '今开'?: number
  '昨收'?: number
  '最高'?: number
  '最低'?: number
  '振幅'?: number
  '换手率'?: number
  '成交额'?: number
  '市盈率-动态'?: number
  '市净率'?: number
  '总市值'?: number
  '流通市值'?: number
  '所属行业'?: string
  '名称'?: string
  '最新价'?: number
  [key: string]: unknown
}

export interface AnalysisDetails {
  [key: string]: unknown
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
    details: AnalysisDetails
  }
  trading_signal: TradingSignal
  price_prediction: PricePrediction
  validation?: AnalysisValidation
  indicators: Indicators
  position_strategy: PositionStrategyHeld | PositionStrategyNotHeld
  stock_info: StockInfo
  market_data?: Record<string, unknown>
  charts: {
    kline: KlineData
    technical: TechnicalChartData
    fund_flow: FundFlowData
  }
  hmm_state?: HmmState
  analysis_log?: LogEntry[]
}

export interface BacktestRequest {
  stock_code: string
}

export interface BacktestPrediction {
  date: string
  current_price: number | null
  trend: TrendType
  day1_pred_high: number | null
  day1_pred_low: number | null
  day2_pred_high: number | null
  day2_pred_low: number | null
  actual_day1: number | null
  actual_day2: number | null
  day1_hit: boolean | null
  day2_hit: boolean | null
  day1_trend_correct: boolean | null
  day2_trend_correct: boolean | null
  day1_direction_correct: boolean | null
  day2_direction_correct: boolean | null
}

export interface BacktestResult {
  stock_code: string
  data_range: string
  total_predictions: number
  day1_valid_count: number
  day2_valid_count: number
  statistics: {
    day1_hit_rate: number
    day2_hit_rate: number
    day1_trend_accuracy: number
    day2_trend_accuracy: number
    day1_direction_accuracy: number
    day2_direction_accuracy: number
    day1_mean_width_pct: number
    day1_median_width_pct: number
    day1_midpoint_mae_pct: number
    day1_coverage_width_score: number
    day2_mean_width_pct: number
    day2_median_width_pct: number
    day2_midpoint_mae_pct: number
    day2_coverage_width_score: number
  }
  predictions: BacktestPrediction[]
}

export interface BatchAnalysisRequest {
  stocks: AnalysisRequest[]
}

export interface BatchAnalysisResult {
  results: AnalysisResult[]
  errors: Array<{ stock_input: string; error: string }>
}

export interface BatchQuickSummary {
  stock_code: string
  stock_name: string
  signal_text: string
  score: number
  action_gate: string
  recommendation: string
  index: number
}

export interface ProgressMessage {
  type: 'progress'
  task_id: string
  current: number
  total: number
  current_stock: string
  status: 'analyzing' | 'completed' | 'error'
}

export interface WalkForwardWindow {
  window_id: number
  train_start: string
  train_end: string
  test_start: string
  test_end: string
  hit_rate: number
  direction_accuracy: number
  trend_accuracy: number
  n_predictions: number
}

export interface WalkForwardResult {
  stock_code: string
  train_window: number
  test_window: number
  step: number
  total_predictions: number
  windows: WalkForwardWindow[]
  overall: {
    avg_hit_rate: number
    avg_direction_accuracy: number
    avg_trend_accuracy: number
  }
  stability: {
    hit_rate_std: number
    direction_accuracy_std: number
    trend_accuracy_std: number
    sharpe_ratio: number
  }
}

export interface WalkForwardRequest {
  stock_code: string
  train_window?: number
  test_window?: number
  step?: number
}

export interface MlPrediction {
  next_day_return?: number | null
  volatility?: number | null
  direction?: number | null
  confidence?: number | null
}

export interface HmmState {
  current_state: string
  state_probabilities: Record<string, number>
  transition_matrix?: number[][] | null
}

export interface MarketStatus {
  indexChange: number | null
  sentiment: string
  volatilityState: string
  riskLevel: string
  hmmState: string | null
}

export interface RiskAssessment {
  var95: number | null
  var99: number | null
  cvar95: number | null
  cvar99: number | null
  tailRiskWarning: string | null
}

export interface PredictionResult {
  hybridPrediction: {
    day1Low: number | null
    day1High: number | null
    day2Low: number | null
    day2High: number | null
  }
  rulePrediction: {
    day1Low: number | null
    day1High: number | null
    day2Low: number | null
    day2High: number | null
  } | null
  mlPrediction: MlPrediction | null
  alpha: number | null
  confidence: number | null
  day1Trend: string | null
  day2Trend: string | null
}

export function getErrorMessage(error: unknown, fallback = '操作失败'): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'object' && error !== null) {
    const e = error as { response?: { data?: { detail?: string } }; message?: string }
    return e.response?.data?.detail || e.message || fallback
  }
  return fallback
}
