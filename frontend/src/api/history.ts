import axios from 'axios'
import type { WatchlistItem, StockInput } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const response = await api.get('/api/watchlist')
  return response.data
}

export async function addToWatchlist(data: StockInput): Promise<WatchlistItem> {
  const response = await api.post('/api/watchlist', data)
  return response.data
}

export async function updateWatchlist(stockCode: string, data: Partial<StockInput>): Promise<WatchlistItem> {
  const response = await api.put(`/api/watchlist/${stockCode}`, data)
  return response.data
}

export async function removeFromWatchlist(stockCode: string): Promise<void> {
  await api.delete(`/api/watchlist/${stockCode}`)
}
