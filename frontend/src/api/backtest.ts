import axios from 'axios'
import type { BacktestRequest, BacktestResult } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 120000,
})

export async function runBacktest(data: BacktestRequest): Promise<BacktestResult> {
  const response = await api.post('/api/backtest', data)
  return response.data
}
