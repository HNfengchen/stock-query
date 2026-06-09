import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { AnalysisRequest, BatchQuickSummary } from '@/types'
import { batchAnalyze, batchQuickAnalyzeStream } from '@/api/analysis'
import { useWatchlistStore } from './watchlistStore'
import { useAnalysisStore } from './analysisStore'
import { useLogStore } from './logStore'
import { getLogger } from '@/utils/logger'

export const useBatchStore = defineStore('batch', () => {
  const logger = getLogger('store.batch')
  const batchProgress = reactive({ current: 0, total: 0, currentStock: '', status: '' as 'analyzing' | 'completed' | 'error' | '' })
  const batchError = ref<string>('')
  const batchErrorStocks = ref<Array<{ stock_input: string; error: string }>>([])

  let batchAbortController: AbortController | null = null

  async function runBatchAnalysis(stocks: AnalysisRequest[]) {
    const analysisStore = useAnalysisStore()
    analysisStore.setLoading(true)
    batchProgress.current = 0
    batchProgress.total = stocks.length
    batchProgress.currentStock = ''
    batchProgress.status = 'analyzing'
    try {
      const result = await batchAnalyze({ stocks })
      batchProgress.status = 'completed'
      return result
    } catch (e) {
      batchProgress.status = 'error'
      throw e
    } finally {
      analysisStore.setLoading(false)
    }
  }

  async function runBatchQuickAnalysis(stocks: AnalysisRequest[]) {
    const analysisStore = useAnalysisStore()
    const watchlistStore = useWatchlistStore()
    const logStore = useLogStore()
    analysisStore.setLoading(true)
    batchError.value = ''
    batchErrorStocks.value = []
    batchAbortController = new AbortController()
    batchProgress.current = 0
    batchProgress.total = stocks.length
    batchProgress.currentStock = ''
    batchProgress.status = 'analyzing'
    logger.info(`开始批量分析: ${stocks.length} 只股票`)

    try {
      await batchQuickAnalyzeStream(
        stocks,
        (event) => {
          if (event.type === 'analyzing' && event.stock_input) {
            batchProgress.currentStock = event.stock_input
            // analyzing事件的current是索引(0-based)，不用于进度条
            // 进度条只由completed事件驱动
          }
          logger.info(`Batch进度: type=${event.type}, current=${event.current}/${event.total}`)
          if (event.type === 'completed' && event.summary) {
            // completed事件的current是已完成数(1-based)，用于进度条
            batchProgress.current = event.current
            batchProgress.total = event.total
            batchProgress.currentStock = event.summary.stock_name || event.summary.stock_code
            watchlistStore.updateItemSignal(
              event.summary.stock_code,
              event.summary.signal_text,
              event.summary.score,
            )
            // 将批量分析结果设置到analysisStore，使面板数据可用
            const s = event.summary as BatchQuickSummary
            if (s.validation || s.stock_info || s.indicators) {
              analysisStore.setAnalysisResult({
                stock_code: s.stock_code,
                stock_name: s.stock_name,
                analysis: s.analysis || { technical_score: 0, fund_flow_score: 0, sentiment_score: 0, overall_score: 0, recommendation: s.recommendation, details: {} },
                trading_signal: { score: s.score, signal: s.action_gate, signal_text: s.signal_text },
                validation: s.validation,
                price_prediction: s.price_prediction || { current: null, support: null, resistance: null, day1: { target_low: null, target_high: null, trend: 'neutral', signal: '' }, day2: { target_low: null, target_high: null, trend: 'neutral', signal: '' } },
                indicators: s.indicators || {},
                position_strategy: s.position_strategy || {},
                stock_info: s.stock_info,
                market_data: s.market_data,
                hmm_state: s.hmm_state,
                charts: { kline: { dates: [], opens: [], closes: [], highs: [], lows: [], volumes: [], ma5: [], ma10: [], ma20: [], ma60: [], boll_upper: [], boll_middle: [], boll_lower: [] }, technical: { dates: [], macd: [], dif: [], dea: [], rsi6: [], rsi12: [], k: [], d: [], j: [] }, fund_flow: { dates: [], main_flow: [], main_flow_ratio: [], small_flow: [], change_pct: [] } },
              })
            }
          }
          if (event.type === 'error' && event.error) {
            batchProgress.current = event.current
            batchErrorStocks.value.push({
              stock_input: event.error.stock_input,
              error: event.error.error,
            })
          }
        },
        (event) => {
          logger.info(`Batch完成: success=${event.success_count}, error=${event.error_count}`)
          batchProgress.status = 'completed'
          batchProgress.current = event.total
          if (event.error_count > 0) {
            batchError.value = `${event.error_count}只股票分析失败`
            batchErrorStocks.value = event.errors || []
          }
        },
        (error) => {
          logger.info('Batch错误:', error)
          batchProgress.status = 'error'
          batchError.value = error
        },
        batchAbortController.signal,
      )
    } finally {
      analysisStore.setLoading(false)
      batchAbortController = null
    }
  }

  function cancelBatchAnalysis() {
    const analysisStore = useAnalysisStore()
    if (batchAbortController) {
      batchAbortController.abort()
      batchAbortController = null
      batchProgress.status = ''
      analysisStore.setLoading(false)
    }
  }

  return {
    batchProgress,
    batchError,
    batchErrorStocks,
    runBatchAnalysis,
    runBatchQuickAnalysis,
    cancelBatchAnalysis,
  }
})
