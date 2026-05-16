import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BacktestRequest, BacktestResult, WalkForwardRequest, WalkForwardResult } from '@/types'
import { runBacktest, runWalkForward } from '@/api/backtest'

export const useBacktestStore = defineStore('backtest', () => {
  const result = ref<BacktestResult | null>(null)
  const loading = ref(false)
  const error = ref('')

  const wfResult = ref<WalkForwardResult | null>(null)
  const wfLoading = ref(false)
  const wfError = ref('')

  async function executeBacktest(data: BacktestRequest) {
    loading.value = true
    error.value = ''
    try {
      const res = await runBacktest(data)
      result.value = res
      return res
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '预测验证执行失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function executeWalkForward(data: WalkForwardRequest) {
    wfLoading.value = true
    wfError.value = ''
    try {
      const res = await runWalkForward(data)
      wfResult.value = res
      return res
    } catch (e: any) {
      wfError.value = e.response?.data?.detail || e.message || 'Walk-Forward验证执行失败'
      throw e
    } finally {
      wfLoading.value = false
    }
  }

  function clearResult() {
    result.value = null
    error.value = ''
  }

  function clearWalkForward() {
    wfResult.value = null
    wfError.value = ''
  }

  return {
    result,
    loading,
    error,
    executeBacktest,
    clearResult,
    wfResult,
    wfLoading,
    wfError,
    executeWalkForward,
    clearWalkForward,
  }
})
