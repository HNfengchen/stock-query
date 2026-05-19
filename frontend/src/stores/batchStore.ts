import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AnalysisRequest } from '@/types'
import { batchAnalyze, batchQuickAnalyzeStream } from '@/api/analysis'
import { useWatchlistStore } from './watchlistStore'
import { useAnalysisStore } from './analysisStore'
import { useLogStore } from './logStore'

export const useBatchStore = defineStore('batch', () => {
  const batchProgress = ref({ current: 0, total: 0, currentStock: '', status: '' as 'analyzing' | 'completed' | 'error' | '' })
  const batchError = ref<string>('')
  const batchErrorStocks = ref<Array<{ stock_input: string; error: string }>>([])

  let batchAbortController: AbortController | null = null

  async function runBatchAnalysis(stocks: AnalysisRequest[]) {
    const analysisStore = useAnalysisStore()
    analysisStore.setLoading(true)
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }
    try {
      const result = await batchAnalyze({ stocks })
      batchProgress.value.status = 'completed'
      return result
    } catch (e) {
      batchProgress.value.status = 'error'
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
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }

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
            watchlistStore.updateItemSignal(
              event.summary.stock_code,
              event.summary.signal_text,
              event.summary.score,
            )
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
      analysisStore.setLoading(false)
      batchAbortController = null
    }
  }

  function cancelBatchAnalysis() {
    const analysisStore = useAnalysisStore()
    if (batchAbortController) {
      batchAbortController.abort()
      batchAbortController = null
      batchProgress.value.status = ''
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
