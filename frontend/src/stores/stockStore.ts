import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AnalysisResult, WatchlistItem, AnalysisRequest } from '@/types'
import { analyzeStock, batchAnalyze, batchQuickAnalyzeStream } from '@/api/analysis'
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlist } from '@/api/history'

export const useStockStore = defineStore('stock', () => {
  const currentResult = ref<AnalysisResult | null>(null)
  const watchlist = ref<WatchlistItem[]>([])
  const loading = ref(false)
  const batchProgress = ref({ current: 0, total: 0, currentStock: '', status: '' as 'analyzing' | 'completed' | 'error' | '' })

  const hasResult = computed(() => currentResult.value !== null)

  async function runAnalysis(data: AnalysisRequest) {
    loading.value = true
    try {
      const result = await analyzeStock(data)
      currentResult.value = result
      return result
    } finally {
      loading.value = false
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
    batchProgress.value = { current: 0, total: stocks.length, currentStock: '', status: 'analyzing' }
    try {
      await batchQuickAnalyzeStream(
        stocks,
        (event) => {
          batchProgress.value.current = event.current
          batchProgress.value.total = event.total
          if (event.summary) {
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
        },
        (event) => {
          batchProgress.value.status = 'completed'
          batchProgress.value.current = event.total
        },
        (error) => {
          batchProgress.value.status = 'error'
          console.error('Batch quick analysis error:', error)
        },
      )
    } finally {
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

  function clearResult() {
    currentResult.value = null
  }

  return {
    currentResult,
    watchlist,
    loading,
    batchProgress,
    hasResult,
    runAnalysis,
    runBatchAnalysis,
    runBatchQuickAnalysis,
    loadWatchlist,
    addStock,
    removeStock,
    updateStock,
    clearResult,
  }
})
