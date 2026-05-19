import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { LogEntry } from '@/types'

export const useLogStore = defineStore('log', () => {
  const analysisLogs = ref<LogEntry[]>([])

  const MAX_LOG_ENTRIES = 500

  function addLog(entry: LogEntry) {
    analysisLogs.value.push(entry)
    if (analysisLogs.value.length > MAX_LOG_ENTRIES) {
      analysisLogs.value.splice(0, analysisLogs.value.length - MAX_LOG_ENTRIES)
    }
  }

  function clearLogs() {
    analysisLogs.value = []
  }

  return {
    analysisLogs,
    addLog,
    clearLogs,
  }
})
