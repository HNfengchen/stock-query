import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useAnalysisStore } from './analysisStore'
import { useWatchlistStore } from './watchlistStore'
import { useBatchStore } from './batchStore'
import { useLogStore } from './logStore'

export const useStockStore = defineStore('stock', () => {
  const analysis = useAnalysisStore()
  const watchlist = useWatchlistStore()
  const batch = useBatchStore()
  const log = useLogStore()

  return {
    currentResult: computed(() => analysis.currentResult),
    loading: computed(() => analysis.loading),
    hasResult: computed(() => analysis.hasResult),
    streamStage: computed(() => analysis.streamStage),
    streamStageData: computed(() => analysis.streamStageData),
    marketStatus: computed(() => analysis.marketStatus),
    riskAssessment: computed(() => analysis.riskAssessment),
    predictionResult: computed(() => analysis.predictionResult),
    runAnalysis: analysis.runAnalysis,
    cancelAnalysis: analysis.cancelAnalysis,
    cancelStreamAnalysis: analysis.cancelStreamAnalysis,
    clearResult: analysis.clearResult,
    watchlist: computed(() => watchlist.watchlist),
    loadWatchlist: watchlist.loadWatchlist,
    addStock: watchlist.addStock,
    removeStock: watchlist.removeStock,
    updateStock: watchlist.updateStock,
    batchProgress: batch.batchProgress,
    batchError: computed(() => batch.batchError),
    batchErrorStocks: computed(() => batch.batchErrorStocks),
    runBatchAnalysis: batch.runBatchAnalysis,
    runBatchQuickAnalysis: batch.runBatchQuickAnalysis,
    cancelBatchAnalysis: batch.cancelBatchAnalysis,
    analysisLogs: computed(() => log.analysisLogs),
    addLog: log.addLog,
    clearLogs: log.clearLogs,
  }
})

export { useAnalysisStore } from './analysisStore'
export { useWatchlistStore } from './watchlistStore'
export { useBatchStore } from './batchStore'
export { useLogStore } from './logStore'
