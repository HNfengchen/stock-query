import { defineStore } from 'pinia'
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
    currentResult: analysis.currentResult,
    loading: analysis.loading,
    hasResult: analysis.hasResult,
    streamStage: analysis.streamStage,
    streamStageData: analysis.streamStageData,
    marketStatus: analysis.marketStatus,
    riskAssessment: analysis.riskAssessment,
    predictionResult: analysis.predictionResult,
    runAnalysis: analysis.runAnalysis,
    cancelAnalysis: analysis.cancelAnalysis,
    cancelStreamAnalysis: analysis.cancelStreamAnalysis,
    clearResult: analysis.clearResult,
    watchlist: watchlist.watchlist,
    loadWatchlist: watchlist.loadWatchlist,
    addStock: watchlist.addStock,
    removeStock: watchlist.removeStock,
    updateStock: watchlist.updateStock,
    batchProgress: batch.batchProgress,
    batchError: batch.batchError,
    batchErrorStocks: batch.batchErrorStocks,
    runBatchAnalysis: batch.runBatchAnalysis,
    runBatchQuickAnalysis: batch.runBatchQuickAnalysis,
    cancelBatchAnalysis: batch.cancelBatchAnalysis,
    analysisLogs: log.analysisLogs,
    addLog: log.addLog,
    clearLogs: log.clearLogs,
  }
})

export { useAnalysisStore } from './analysisStore'
export { useWatchlistStore } from './watchlistStore'
export { useBatchStore } from './batchStore'
export { useLogStore } from './logStore'
