import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AnalysisResult, WatchlistItem, AnalysisRequest, MarketStatus, RiskAssessment, PredictionResult, LogEntry } from '@/types'
import { analyzeStock, batchAnalyze, batchQuickAnalyzeStream } from '@/api/analysis'
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlist } from '@/api/history'

export const useStockStore = defineStore('stock', () => {
  const currentResult = ref<AnalysisResult | null>(null)
  const analysisLogs = ref<LogEntry[]>([])
  const watchlist = ref<WatchlistItem[]>([])
  const loading = ref(false)
  const batchProgress = ref({ current: 0, total: 0, currentStock: '', status: '' as 'analyzing' | 'completed' | 'error' | '' })
  const batchError = ref<string>('')
  const batchErrorStocks = ref<Array<{ stock_input: string; error: string }>>([])

  let batchAbortController: AbortController | null = null
  let streamAbortController: AbortController | null = null

  const streamStage = ref<string>('')
  const streamStageData = ref<Record<string, any>>({})
  const cockpitMode = ref(false)

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
    if (!r) return { var95: null, var99: null, cvar95: null, cvar99: null, stressTest: null, tailRiskWarning: null }

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

    return { var95, var99, cvar95, cvar99, stressTest: r.validation?.stress_test || null, tailRiskWarning }
  })

  const predictionResult = computed<PredictionResult>(() => {
    const r = currentResult.value
    if (!r) return {
      hybridPrediction: { day1Low: null, day1High: null, day2Low: null, day2High: null },
      rulePrediction: null,
      mlPrediction: null,
      alpha: null,
      confidence: null,
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

      if (hybridPrediction.day1Low != null && hybridPrediction.day1High != null && alpha > 0) {
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
    }
  })

  async function runAnalysis(data: AnalysisRequest) {
    loading.value = true
    try {
      await new Promise<void>((resolve, reject) => {
        const controller = new AbortController()
        streamAbortController = controller
        streamStage.value = 'stage_basic'
        streamStageData.value = {}

        const params = new URLSearchParams({
          stock_input: data.stock_input,
          position_status: data.position_status,
        })
        if (data.cost_price != null) {
          params.set('cost_price', String(data.cost_price))
        }

        let timeoutId: ReturnType<typeof setTimeout>
        const resetTimeout = () => {
          clearTimeout(timeoutId)
          timeoutId = setTimeout(() => {
            controller.abort()
            reject(new Error('流式分析超时，正在尝试普通接口...'))
          }, 120000)
        }
        resetTimeout()

        let sseFailed = false

        fetch(`/api/analysis/stream?${params.toString()}`, { signal: controller.signal })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`)
            }
            const reader = response.body?.getReader()
            if (!reader) {
              throw new Error('No response body')
            }
            const decoder = new TextDecoder()
            let buffer = ''
            let currentEvent = ''

            const processChunk = (): Promise<void> => {
              return reader.read().then(({ done, value }) => {
                if (done) {
                  clearTimeout(timeoutId)
                  loading.value = false
                  streamAbortController = null
                  resolve()
                  return
                }
                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() || ''

                let hasActivity = false
                for (const line of lines) {
                  if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim()
                    hasActivity = true
                  } else if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6)
                    hasActivity = true
                    try {
                      const eventData = JSON.parse(dataStr)
                      if (currentEvent === 'stage_basic') {
                        streamStage.value = 'stage_basic'
                        streamStageData.value = { ...streamStageData.value, basic: eventData }
                        if (currentResult.value) {
                          if (eventData.stock_info) currentResult.value.stock_info = eventData.stock_info
                        } else if (eventData.stock_info) {
                          currentResult.value = {
                            stock_code: '', stock_name: '', analysis: { technical_score: 0, fund_flow_score: 0, sentiment_score: 0, overall_score: 0, recommendation: '', details: {} },
                            trading_signal: { score: 0, signal: '', signal_text: '' },
                            price_prediction: { current: null, support: null, resistance: null, day1: { target_low: null, target_high: null, trend: 'neutral', signal: '' }, day2: { target_low: null, target_high: null, trend: 'neutral', signal: '' } },
                            indicators: {}, position_strategy: {}, stock_info: eventData.stock_info,
                            charts: { kline: { dates: [], opens: [], closes: [], highs: [], lows: [], volumes: [], ma5: [], ma10: [], ma20: [], ma60: [], boll_upper: [], boll_middle: [], boll_lower: [] }, technical: { dates: [], macd: [], dif: [], dea: [], rsi6: [], rsi12: [], k: [], d: [], j: [] }, fund_flow: { dates: [], main_flow: [], main_flow_ratio: [], small_flow: [], change_pct: [] } },
                          }
                        }
                      } else if (currentEvent === 'stage_technical') {
                        streamStage.value = 'stage_technical'
                        streamStageData.value = { ...streamStageData.value, technical: eventData }
                        if (currentResult.value) {
                          if (eventData.indicators) currentResult.value.indicators = eventData.indicators
                          if (eventData.technical_chart_data) {
                            currentResult.value.charts = { ...currentResult.value.charts, ...eventData.technical_chart_data }
                          }
                        }
                      } else if (currentEvent === 'stage_risk') {
                        streamStage.value = 'stage_risk'
                        streamStageData.value = { ...streamStageData.value, risk: eventData }
                        if (currentResult.value) {
                          if (eventData.signal) currentResult.value.trading_signal = eventData.signal
                          if (eventData.validation) {
                            if (currentResult.value.validation) {
                              currentResult.value.validation = { ...currentResult.value.validation, ...eventData.validation }
                            } else {
                              currentResult.value.validation = eventData.validation
                            }
                          }
                          if (eventData.tech_score != null || eventData.fund_score != null || eventData.sentiment_score != null) {
                            currentResult.value.analysis = {
                              ...currentResult.value.analysis,
                              technical_score: eventData.tech_score ?? currentResult.value.analysis.technical_score,
                              fund_flow_score: eventData.fund_score ?? currentResult.value.analysis.fund_flow_score,
                              sentiment_score: eventData.sentiment_score ?? currentResult.value.analysis.sentiment_score,
                            }
                          }
                        }
                      } else if (currentEvent === 'stage_prediction') {
                        streamStage.value = 'stage_prediction'
                        streamStageData.value = { ...streamStageData.value, prediction: eventData }
                        if (currentResult.value) {
                          if (eventData.price_prediction) currentResult.value.price_prediction = eventData.price_prediction
                          if (eventData.position_strategy) currentResult.value.position_strategy = eventData.position_strategy
                        }
                      } else if (currentEvent === 'stage_complete') {
                        currentResult.value = eventData
                        streamStage.value = 'stage_complete'
                        clearTimeout(timeoutId)
                        loading.value = false
                        streamAbortController = null
                        resolve()
                        return
                      } else if (currentEvent === 'log') {
                        addLog(eventData)
                      } else if (currentEvent === 'stress_test_result') {
                        if (currentResult.value?.validation) {
                          currentResult.value.validation.stress_test = eventData
                        }
                      } else if (currentEvent === 'error') {
                        clearTimeout(timeoutId)
                        loading.value = false
                        streamAbortController = null
                        reject(new Error(eventData.error || '分析失败'))
                      } else if (currentEvent === 'heartbeat') {
                        // ignore
                      }
                    } catch {
                      // ignore parse errors
                    }
                    currentEvent = ''
                  }
                }
                if (hasActivity) {
                  resetTimeout()
                }
                return processChunk()
              }).catch((e: any) => {
                clearTimeout(timeoutId)
                loading.value = false
                streamAbortController = null
                if (e.name === 'AbortError') {
                  resolve()
                } else {
                  reject(e)
                }
              })
            }

            return processChunk()
          })
          .catch(async (e: any) => {
            clearTimeout(timeoutId)
            if (sseFailed) return
            sseFailed = true
            streamStage.value = ''
            loading.value = true
            try {
              const result = await analyzeStock(data)
              currentResult.value = result
              streamStage.value = 'stage_complete'
              resolve()
            } catch (fallbackErr) {
              reject(fallbackErr)
            } finally {
              loading.value = false
              streamAbortController = null
            }
          })
      })
    } catch (e) {
      loading.value = false
      streamAbortController = null
      throw e
    }
  }

  async function runBatchAnalysis(stocks: AnalysisRequest[]) {
    loading.value = true
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }
    try {
      const result = await batchAnalyze({ stocks })
      batchProgress.value.status = 'completed'
      return result
    } catch (e) {
      batchProgress.value.status = 'error'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function runBatchQuickAnalysis(stocks: AnalysisRequest[]) {
    loading.value = true
    batchError.value = ''
    batchErrorStocks.value = []
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }
    batchAbortController = new AbortController()

    try {
      await batchQuickAnalyzeStream(
        stocks,
        (event) => {
          if (event.type === 'analyzing' && event.stock_input) {
            batchProgress.value.currentStock = event.stock_input
          }
          if (event.type === 'completed' && event.summary) {
            batchProgress.value.current = event.current
            batchProgress.value.total = event.total
            batchProgress.value.currentStock = event.summary.stock_name || event.summary.stock_code
            const idx = watchlist.value.findIndex(w => w.stock_code === event.summary!.stock_code)
            if (idx >= 0) {
              const existing = watchlist.value[idx]!
              watchlist.value[idx] = {
                stock_code: existing.stock_code,
                stock_name: existing.stock_name,
                position_status: existing.position_status,
                cost_price: existing.cost_price,
                added_at: existing.added_at,
                cached_signal: event.summary.signal_text,
                cached_signal_score: event.summary.score,
                cached_signal_time: new Date().toISOString(),
              }
            }
          }
          if (event.type === 'error' && event.error) {
            batchProgress.value.current = event.current
            batchErrorStocks.value.push({
              stock_input: event.error.stock_input,
              error: event.error.error,
            })
          }
        },
        (event) => {
          batchProgress.value.status = 'completed'
          batchProgress.value.current = event.total
          if (event.error_count > 0) {
            batchError.value = `${event.error_count}只股票分析失败`
            batchErrorStocks.value = event.errors || []
          }
        },
        (error) => {
          batchProgress.value.status = 'error'
          batchError.value = error
        },
        batchAbortController.signal,
      )
    } finally {
      loading.value = false
      batchAbortController = null
    }
  }

  function cancelBatchAnalysis() {
    if (batchAbortController) {
      batchAbortController.abort()
      batchAbortController = null
      batchProgress.value.status = ''
      loading.value = false
    }
  }

  function cancelStreamAnalysis() {
    if (streamAbortController) {
      streamAbortController.abort()
      streamAbortController = null
      streamStage.value = ''
      loading.value = false
    }
  }

  async function loadWatchlist() {
    const data = await getWatchlist()
    watchlist.value = data
    return data
  }

  async function addStock(data: AnalysisRequest) {
    const item = await addToWatchlist(data)
    watchlist.value.push(item)
    return item
  }

  async function removeStock(stockCode: string) {
    await removeFromWatchlist(stockCode)
    watchlist.value = watchlist.value.filter(item => item.stock_code !== stockCode)
  }

  async function updateStock(stockCode: string, data: { position_status?: string; cost_price?: number | null }) {
    const item = await updateWatchlist(stockCode, data as any)
    const idx = watchlist.value.findIndex(w => w.stock_code === stockCode)
    if (idx >= 0) {
      watchlist.value[idx] = { ...watchlist.value[idx], ...item }
    }
    return item
  }

  function addLog(entry: LogEntry) {
    analysisLogs.value.push(entry)
  }

  function clearLogs() {
    analysisLogs.value = []
  }

  function clearResult() {
    currentResult.value = null
  }

  return {
    currentResult,
    analysisLogs,
    watchlist,
    loading,
    batchProgress,
    batchError,
    batchErrorStocks,
    streamStage,
    streamStageData,
    cockpitMode,
    hasResult,
    marketStatus,
    riskAssessment,
    predictionResult,
    runAnalysis,
    runBatchAnalysis,
    runBatchQuickAnalysis,
    cancelBatchAnalysis,
    cancelStreamAnalysis,
    loadWatchlist,
    addStock,
    removeStock,
    updateStock,
    clearResult,
    addLog,
    clearLogs,
  }
})
