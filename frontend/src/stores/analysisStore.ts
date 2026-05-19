import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AnalysisResult, AnalysisRequest, MarketStatus, RiskAssessment, PredictionResult, Indicators, PositionStrategyNotHeld, LogEntry, StressTestResult } from '@/types'
import { analyzeStock } from '@/api/analysis'
import { API_TIMEOUTS } from '@/api/config'
import { useLogStore } from './logStore'
import { connectSSEStream } from '@/composables/useSSEStream'
import { getLogger } from '@/utils/logger'

export const useAnalysisStore = defineStore('analysis', () => {
  const logger = getLogger('store.analysis')
  const currentResult = ref<AnalysisResult | null>(null)
  const loading = ref(false)
  const streamStage = ref<string>('')
  const streamStageData = ref<Record<string, unknown>>({})

  let isReentering = false
  let analysisGeneration = 0
  let streamAbortController: AbortController | null = null
  let fallbackAbortController: AbortController | null = null

  const hasResult = computed(() => currentResult.value !== null)

  const marketStatus = computed<MarketStatus>(() => {
    const r = currentResult.value
    if (!r) return { indexChange: null, sentiment: '未知', volatilityState: '未知', riskLevel: '未知', hmmState: null }

    const indexChange = (() => { const v = Number(r.stock_info?.['涨跌幅']); return isNaN(v) ? null : v })()
    const sentimentScore = r.analysis?.sentiment_score ?? 0.5
    let sentiment = '中性'
    if (sentimentScore >= 0.65) sentiment = '乐观'
    else if (sentimentScore <= 0.35) sentiment = '悲观'

    const bollBandwidth = r.indicators?.BOLL?.latest?.bandwidth
    let volatilityState = '正常'
    if (bollBandwidth != null) {
      if (bollBandwidth < 10) volatilityState = '低波动'
      else if (bollBandwidth > 25) volatilityState = '高波动'
    }

    const riskLevel = r.validation?.risk_level || '未知'
    const riskLevelMap: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' }
    const hmmState = r.hmm_state?.current_state || null

    return {
      indexChange,
      sentiment,
      volatilityState,
      riskLevel: riskLevelMap[riskLevel] || riskLevel,
      hmmState,
    }
  })

  const riskAssessment = computed<RiskAssessment>(() => {
    const r = currentResult.value
    if (!r) return { var95: null, var99: null, cvar95: null, cvar99: null, tailRiskWarning: null }

    const dist = r.indicators?.Distribution
    const w20 = dist?.W20 || {}
    const w60 = dist?.W60 || {}
    const distWindow = w20?.var_95?.latest != null ? w20 : w60

    const var95 = distWindow?.var_95?.latest ?? null
    const var99 = distWindow?.var_99?.latest ?? null
    const cvar95 = distWindow?.cvar_95?.latest ?? null
    const cvar99 = distWindow?.cvar_99?.latest ?? null

    const kurtosisSignal = distWindow?.kurtosis?.signal
    let tailRiskWarning: string | null = null
    if (kurtosisSignal === '厚尾') tailRiskWarning = '尾部风险显著，极端波动概率增大'
    else if (kurtosisSignal === '轻尾') tailRiskWarning = '尾部风险较低'

    return { var95, var99, cvar95, cvar99, tailRiskWarning }
  })

  const predictionResult = computed<PredictionResult>(() => {
    const r = currentResult.value
    if (!r) return {
      hybridPrediction: { day1Low: null, day1High: null, day2Low: null, day2High: null },
      rulePrediction: null,
      mlPrediction: null,
      alpha: null,
      confidence: null,
      day1Trend: null,
      day2Trend: null,
    }

    const pp = r.price_prediction
    const hybridPrediction = {
      day1Low: pp?.day1?.target_low ?? null,
      day1High: pp?.day1?.target_high ?? null,
      day2Low: pp?.day2?.target_low ?? null,
      day2High: pp?.day2?.target_high ?? null,
    }

    const mlPred = pp?.ml_prediction
    const alpha = pp?.hybrid_alpha ?? null
    const confidence = pp?.validation_confidence ?? null

    let rulePrediction: PredictionResult['rulePrediction'] = null
    if (mlPred && alpha != null && alpha < 1.0 && pp?.current) {
      const current = pp.current
      const mlReturn = mlPred.next_day_return ?? 0
      const mlVol = mlPred.volatility ?? 0
      const mlLow = current * (1 + mlReturn - mlVol)
      const mlHigh = current * (1 + mlReturn + mlVol)

      if (hybridPrediction.day1Low != null && hybridPrediction.day1High != null && alpha > 0.01) {
        const ruleLow = (hybridPrediction.day1Low - (1 - alpha) * mlLow) / alpha
        const ruleHigh = (hybridPrediction.day1High - (1 - alpha) * mlHigh) / alpha
        rulePrediction = {
          day1Low: ruleLow,
          day1High: ruleHigh,
          day2Low: hybridPrediction.day2Low,
          day2High: hybridPrediction.day2High,
        }
      }
    }

    return {
      hybridPrediction,
      rulePrediction,
      mlPrediction: mlPred || null,
      alpha,
      confidence,
      day1Trend: pp?.day1?.trend ?? null,
      day2Trend: pp?.day2?.trend ?? null,
    }
  })

  async function runAnalysis(data: AnalysisRequest) {
    if (loading.value) {
      cancelAnalysis()
    }
    const gen = ++analysisGeneration
    currentResult.value = null
    streamStage.value = ''
    streamStageData.value = {}
    loading.value = true
    const logStore = useLogStore()
    logger.info('开始分析: stock_input=' + data.stock_input)

    const controller = new AbortController()
    streamAbortController = controller

    const params = new URLSearchParams({
      stock_input: data.stock_input,
      position_status: data.position_status,
    })
    if (data.cost_price != null) {
      params.set('cost_price', String(data.cost_price))
    }

    let sseFailed = false

    try {
      try {
        logger.info('SSE连接已建立')
        await connectSSEStream({
          url: `/api/analysis/stream?${params.toString()}`,
          timeout: API_TIMEOUTS.sse,
          signal: controller.signal,
          onEvent: ({ event, data: eventData }) => {
            if (gen !== analysisGeneration) return
            logger.info(`SSE事件: ${event}, stage=${streamStage.value}`)

            if (event === 'stage_basic') {
              streamStage.value = 'stage_basic'
              streamStageData.value = { ...streamStageData.value, basic: eventData }
              if (currentResult.value) {
                if ((eventData as any).stock_info) currentResult.value.stock_info = (eventData as any).stock_info
              } else if ((eventData as any).stock_info) {
                currentResult.value = {
                  stock_code: '', stock_name: '', analysis: { technical_score: 0, fund_flow_score: 0, sentiment_score: 0, overall_score: 0, recommendation: '', details: {} },
                  trading_signal: { score: 0, signal: '', signal_text: '' },
                  price_prediction: { current: null, support: null, resistance: null, day1: { target_low: null, target_high: null, trend: 'neutral', signal: '' }, day2: { target_low: null, target_high: null, trend: 'neutral', signal: '' } },
                  indicators: {} as Indicators, position_strategy: {} as PositionStrategyNotHeld, stock_info: (eventData as any).stock_info,
                  charts: { kline: { dates: [], opens: [], closes: [], highs: [], lows: [], volumes: [], ma5: [], ma10: [], ma20: [], ma60: [], boll_upper: [], boll_middle: [], boll_lower: [] }, technical: { dates: [], macd: [], dif: [], dea: [], rsi6: [], rsi12: [], k: [], d: [], j: [] }, fund_flow: { dates: [], main_flow: [], main_flow_ratio: [], small_flow: [], change_pct: [] } },
                }
              }
            } else if (event === 'stage_technical') {
              streamStage.value = 'stage_technical'
              streamStageData.value = { ...streamStageData.value, technical: eventData }
              if (currentResult.value) {
                if ((eventData as any).indicators) currentResult.value.indicators = (eventData as any).indicators
                if ((eventData as any).technical_chart_data) {
                  currentResult.value.charts = { ...currentResult.value.charts, ...(eventData as any).technical_chart_data }
                }
              }
            } else if (event === 'stage_risk') {
              streamStage.value = 'stage_risk'
              streamStageData.value = { ...streamStageData.value, risk: eventData }
              if (currentResult.value) {
                if ((eventData as any).signal) currentResult.value.trading_signal = (eventData as any).signal
                if ((eventData as any).validation) {
                  if (currentResult.value.validation) {
                    currentResult.value.validation = { ...currentResult.value.validation, ...(eventData as any).validation }
                  } else {
                    currentResult.value.validation = (eventData as any).validation
                  }
                }
                if ((eventData as any).tech_score != null || (eventData as any).fund_score != null || (eventData as any).sentiment_score != null) {
                  currentResult.value.analysis = {
                    ...currentResult.value.analysis,
                    technical_score: (eventData as any).tech_score ?? currentResult.value.analysis.technical_score,
                    fund_flow_score: (eventData as any).fund_score ?? currentResult.value.analysis.fund_flow_score,
                    sentiment_score: (eventData as any).sentiment_score ?? currentResult.value.analysis.sentiment_score,
                  }
                }
              }
            } else if (event === 'stage_prediction') {
              streamStage.value = 'stage_prediction'
              streamStageData.value = { ...streamStageData.value, prediction: eventData }
              if (currentResult.value) {
                if ((eventData as any).price_prediction) currentResult.value.price_prediction = (eventData as any).price_prediction
                if ((eventData as any).position_strategy) currentResult.value.position_strategy = (eventData as any).position_strategy
              }
            } else if (event === 'stage_complete') {
              if (gen !== analysisGeneration) return
              const completeData = eventData as AnalysisResult
              if (completeData && 'error' in completeData && !completeData.stock_code) {
                logger.warn('stage_complete 包含错误:', (completeData as any).error)
                throw new Error((completeData as any).error || '分析失败')
              }
              currentResult.value = completeData
              streamStage.value = 'stage_complete'
            } else if (event === 'log') {
              logStore.addLog(eventData as LogEntry)
            } else if (event === 'stress_test_result') {
              if (currentResult.value?.validation) {
                currentResult.value.validation.stress_test = eventData as StressTestResult
              }
            } else if (event === 'error') {
              throw new Error((eventData as any).error || '分析失败')
            }
          },
          onComplete: () => {
            if (gen === analysisGeneration) {
              loading.value = false
              streamAbortController = null
            }
          },
        })
        return
      } catch (sseError) {
        logger.info('SSE失败，回退到普通API:', sseError)
        if (sseFailed) return
        if (gen !== analysisGeneration) {
          streamAbortController = null
          isReentering = false
          return
        }
        sseFailed = true
      }

      streamStage.value = ''
      loading.value = true
      clearResult()
      const fbController = new AbortController()
      fallbackAbortController = fbController
      isReentering = true
      try {
        const result = await analyzeStock(data, fbController.signal)
        if (gen !== analysisGeneration || fbController.signal.aborted) return
        logger.info('Fallback API成功，stock_code=' + result.stock_code)
        currentResult.value = result
        streamStage.value = 'stage_complete'
        // Fallback 成功后写入分析日志到 logStore
        if (result?.analysis_log && Array.isArray(result.analysis_log)) {
          for (const entry of result.analysis_log) {
            logStore.addLog(entry as LogEntry)
          }
        }
      } catch (fallbackErr) {
        logger.info('Fallback API失败:', fallbackErr)
        throw fallbackErr
      } finally {
        if (gen === analysisGeneration) {
          loading.value = false
          streamAbortController = null
          fallbackAbortController = null
          isReentering = false
        }
      }
    } catch (e) {
      logger.error('分析异常:', e)
      loading.value = false
      streamAbortController = null
      isReentering = false
      throw e
    }
  }

  function cancelAnalysis() {
    analysisGeneration++
    if (streamAbortController) {
      streamAbortController.abort()
      streamAbortController = null
    }
    if (fallbackAbortController) {
      fallbackAbortController.abort()
      fallbackAbortController = null
    }
    streamStage.value = ''
    loading.value = false
    isReentering = false
  }

  function cancelStreamAnalysis() {
    if (streamAbortController) {
      streamAbortController.abort()
      streamAbortController = null
      streamStage.value = ''
      loading.value = false
    }
  }

  function clearResult() {
    currentResult.value = null
  }

  function setLoading(value: boolean) {
    loading.value = value
  }

  return {
    currentResult,
    loading,
    streamStage,
    streamStageData,
    hasResult,
    marketStatus,
    riskAssessment,
    predictionResult,
    runAnalysis,
    cancelAnalysis,
    cancelStreamAnalysis,
    clearResult,
    setLoading,
  }
})
