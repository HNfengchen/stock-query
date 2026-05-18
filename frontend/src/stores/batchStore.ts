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
    analysisStore.loading = true
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }
    try {
      const result = await batchAnalyze({ stocks })
      batchProgress.value.status = 'completed'
      return result
    } catch (e) {
      batchProgress.value.status = 'error'
      throw e
    } finally {
      analysisStore.loading = false
    }
  }

  async function runBatchQuickAnalysis(stocks: AnalysisRequest[]) {
    const analysisStore = useAnalysisStore()
    const watchlistStore = useWatchlistStore()
    const logStore = useLogStore()
    analysisStore.loading = true
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
            const idx = watchlistStore.watchlist.findIndex(w => w.stock_code === event.summary!.stock_code)
            if (idx >= 0) {
              const existing = watchlistStore.watchlist[idx]!
              watchlistStore.watchlist[idx] = {
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
      analysisStore.loading = false
      batchAbortController = null
    }
  }

  function cancelBatchAnalysis() {
    const analysisStore = useAnalysisStore()
    if (batchAbortController) {
      batchAbortController.abort()
      batchAbortController = null
      batchProgress.value.status = ''
      analysisStore.loading = false
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
