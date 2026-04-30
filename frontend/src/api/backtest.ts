import axios from 'axios'
import type { BacktestRequest, BacktestResult } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 120000,
})

export async function runBacktest(data: BacktestRequest): Promise<BacktestResult> {
  const endpoint = data.mode === 'custom' ? '/api/backtest/custom' : '/api/backtest'
  const response = await api.post(endpoint, data)
  return response.data
}
