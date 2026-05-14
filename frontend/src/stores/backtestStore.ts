import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { BacktestRequest, BacktestResult } from '@/types'
import { runBacktest } from '@/api/backtest'

export const useBacktestStore = defineStore('backtest', () => {
  const result = ref<BacktestResult | null>(null)
  const loading = ref(false)
  const error = ref('')

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

  function clearResult() {
    result.value = null
    error.value = ''
  }

  return {
    result,
    loading,
    error,
    executeBacktest,
    clearResult,
  }
})
