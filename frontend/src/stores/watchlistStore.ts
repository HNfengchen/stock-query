import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WatchlistItem, StockInput } from '@/types'
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlist } from '@/api/history'

export const useWatchlistStore = defineStore('watchlist', () => {
  const watchlist = ref<WatchlistItem[]>([])

  async function loadWatchlist() {
    const data = await getWatchlist()
    watchlist.value = data
    return data
  }

  async function addStock(data: StockInput) {
    const item = await addToWatchlist(data)
    watchlist.value.push(item)
    return item
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

  return {
    watchlist,
    loadWatchlist,
    addStock,
    removeStock,
    updateStock,
  }
})
