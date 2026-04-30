import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AnalysisResult, WatchlistItem, AnalysisRequest } from '@/types'
import { analyzeStock, batchAnalyze } from '@/api/analysis'
import { getWatchlist, addToWatchlist, removeFromWatchlist } from '@/api/history'

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
    loadWatchlist,
    addStock,
    removeStock,
    clearResult,
  }
})
