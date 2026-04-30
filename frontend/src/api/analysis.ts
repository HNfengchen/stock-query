import axios from 'axios'
import type { AnalysisRequest, AnalysisResult, BatchAnalysisRequest, BatchAnalysisResult } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

export async function analyzeStock(data: AnalysisRequest): Promise<AnalysisResult> {
  const response = await api.post('/api/analysis', data)
  return response.data
}

export async function batchAnalyze(data: BatchAnalysisRequest): Promise<BatchAnalysisResult> {
  const response = await api.post('/api/analysis/batch', data)
  return response.data
}

export function createProgressWebSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/ws/progress/${taskId}`)
}
