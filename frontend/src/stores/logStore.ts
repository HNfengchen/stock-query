import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { LogEntry } from '@/types'

export const useLogStore = defineStore('log', () => {
  const analysisLogs = ref<LogEntry[]>([])

  function addLog(entry: LogEntry) {
    analysisLogs.value.push(entry)
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
