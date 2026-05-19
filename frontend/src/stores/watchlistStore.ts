import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WatchlistItem, StockInput } from '@/types'
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlist } from '@/api/history'
import { getLogger } from '@/utils/logger'

export const useWatchlistStore = defineStore('watchlist', () => {
  const logger = getLogger('store.watchlist')
  const watchlist = ref<WatchlistItem[]>([])

  async function loadWatchlist() {
    logger.info('加载自选股列表')
    try {
      const data = await getWatchlist()
      watchlist.value = data
      logger.info(`自选股加载成功: ${data.length} 只`)
      return data
    } catch (e) {
      logger.error('自选股加载失败:', e)
      watchlist.value = []
      return []
    }
  }

  async function addStock(data: StockInput) {
    logger.info('添加股票: ' + data.stock_input)
    try {
      const item = await addToWatchlist(data)
      watchlist.value.push(item)
      logger.info(`股票添加成功: ${item.stock_code} ${item.stock_name}`)
      return item
    } catch (e) {
      logger.error('股票添加失败:', e)
      throw e
    }
  }

  async function removeStock(stockCode: string) {
    await removeFromWatchlist(stockCode)
    watchlist.value = watchlist.value.filter(item => item.stock_code !== stockCode)
  }

  async function updateStock(stockCode: string, data: { position_status?: string; cost_price?: number | null }) {
    const item = await updateWatchlist(stockCode, data as Partial<StockInput>)
    const idx = watchlist.value.findIndex(w => w.stock_code === stockCode)
    if (idx >= 0) {
      watchlist.value[idx] = { ...watchlist.value[idx], ...item }
    }
    return item
  }

  function updateItemSignal(stockCode: string, signal: string, score: number) {
    const idx = watchlist.value.findIndex(w => w.stock_code === stockCode)
    if (idx >= 0) {
      const existing = watchlist.value[idx]!
      watchlist.value[idx] = {
        stock_code: existing.stock_code,
        stock_name: existing.stock_name,
        position_status: existing.position_status,
        cost_price: existing.cost_price,
        added_at: existing.added_at,
        cached_signal: signal,
        cached_signal_score: score,
        cached_signal_time: new Date().toISOString(),
      }
    }
  }

  return {
    watchlist,
    loadWatchlist,
    addStock,
    removeStock,
    updateStock,
    updateItemSignal,
  }
})
