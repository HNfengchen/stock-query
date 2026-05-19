import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { AnalysisRequest } from '@/types'
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
            // 更新当前分析的索引，让进度条有变化
            if (event.current != null) {
              batchProgress.current = event.current
            }
          }
          logger.info(`Batch进度: type=${event.type}, current=${event.current}/${event.total}`)
          if (event.type === 'completed' && event.summary) {
            batchProgress.current = event.current
            batchProgress.total = event.total
            batchProgress.currentStock = event.summary.stock_name || event.summary.stock_code
            watchlistStore.updateItemSignal(
              event.summary.stock_code,
              event.summary.signal_text,
              event.summary.score,
            )
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
