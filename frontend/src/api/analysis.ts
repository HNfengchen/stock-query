import axios from 'axios'
import type { AnalysisRequest, AnalysisResult, BatchAnalysisRequest, BatchAnalysisResult, BatchQuickSummary } from '@/types'

const api = axios.create({
  baseURL: '',
  timeout: 300000,
})

export async function analyzeStock(data: AnalysisRequest): Promise<AnalysisResult> {
  const response = await api.post('/api/analysis', data)
  return response.data
}

export async function batchAnalyze(data: BatchAnalysisRequest): Promise<BatchAnalysisResult> {
  const response = await api.post('/api/analysis/batch', data)
  return response.data
}

export interface QuickProgressEvent {
  current: number
  total: number
  summary?: BatchQuickSummary
  error?: { stock_input: string; error: string; index: number }
}

export interface QuickCompleteEvent {
  summaries: BatchQuickSummary[]
  errors: Array<{ stock_input: string; error: string; index: number }>
  total: number
}

export async function batchQuickAnalyzeStream(
  stocks: AnalysisRequest[],
  onProgress: (event: QuickProgressEvent) => void,
  onComplete: (event: QuickCompleteEvent) => void,
  onError: (error: string) => void,
): Promise<void> {
  const response = await fetch('/api/analysis/batch-quick', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stocks }),
  })

  if (!response.ok) {
    onError(`HTTP ${response.status}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onError('No response body')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const dataStr = line.slice(6)
        try {
          const data = JSON.parse(dataStr)
          if (currentEvent === 'progress') {
            onProgress(data)
          } else if (currentEvent === 'complete') {
            onComplete(data)
          }
        } catch {
          // ignore parse errors
        }
        currentEvent = ''
      }
    }
  }
}

export function createProgressWebSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/ws/progress/${taskId}`)
}
