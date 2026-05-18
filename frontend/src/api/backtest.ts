import axios from 'axios'
import type { BacktestRequest, BacktestResult, WalkForwardRequest, WalkForwardResult } from '@/types'
import { API_TIMEOUTS } from './config'

const api = axios.create({
  baseURL: '',
  timeout: API_TIMEOUTS.backtest,
})

export async function runBacktest(data: BacktestRequest): Promise<BacktestResult> {
  const response = await api.post('/api/backtest', data)
  return response.data
}

export async function runWalkForward(data: WalkForwardRequest): Promise<WalkForwardResult> {
  const response = await api.post('/api/backtest/walk-forward', data)
  return response.data
}
