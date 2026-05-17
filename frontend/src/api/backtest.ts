import axios from 'axios'
import type { BacktestRequest, BacktestResult, WalkForwardRequest, WalkForwardResult } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 300000,
})

export async function runBacktest(data: BacktestRequest): Promise<BacktestResult> {
  const response = await api.post('/api/backtest', data)
  return response.data
}

export async function runWalkForward(data: WalkForwardRequest): Promise<WalkForwardResult> {
  const response = await api.post('/api/backtest/walk-forward', data)
  return response.data
}
