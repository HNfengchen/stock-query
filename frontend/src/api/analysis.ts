import axios from 'axios'
import type { AnalysisRequest, AnalysisResult, BatchAnalysisRequest, BatchAnalysisResult, BatchQuickSummary } from '@/types'
import { API_TIMEOUTS } from './config'
import { setupAxiosInterceptors } from '@/utils/logger'

const api = axios.create({
  baseURL: '',
  timeout: API_TIMEOUTS.analysis,
})

setupAxiosInterceptors(api)

export async function analyzeStock(data: AnalysisRequest, signal?: AbortSignal): Promise<AnalysisResult> {
  const response = await api.post('/api/analysis', data, { signal })
  return response.data
}

export async function getCachedAnalysis(stockInput: string, positionStatus: string = '未持有', costPrice?: number): Promise<{ cached: boolean; result?: AnalysisResult; age_seconds?: number }> {
  const params: Record<string, string | number> = { stock_input: stockInput, position_status: positionStatus }
  if (costPrice != null) params.cost_price = costPrice
  const response = await api.get('/api/analysis/cache', { params, timeout: 5000 })
  return response.data
}

export async function batchAnalyze(data: BatchAnalysisRequest): Promise<BatchAnalysisResult> {
  const response = await api.post('/api/analysis/batch', data)
  return response.data
}

export interface QuickProgressEvent {
  type: 'analyzing' | 'completed' | 'error'
  current: number
  total: number
  stock_input?: string
  summary?: BatchQuickSummary
  error?: { stock_input: string; error: string; index: number }
  analyzing?: { stock_input: string; index: number }
}

export interface QuickCompleteEvent {
  summaries: BatchQuickSummary[]
  errors: Array<{ stock_input: string; error: string; index: number }>
  total: number
  success_count: number
  error_count: number
}

const SSE_TIMEOUT_MS = API_TIMEOUTS.sse

export async function batchQuickAnalyzeStream(
  stocks: AnalysisRequest[],
  onProgress: (event: QuickProgressEvent) => void,
  onComplete: (event: QuickCompleteEvent) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController()
  let timeoutId: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), SSE_TIMEOUT_MS)

  let aborted = false

  const onExternalAbort = () => {
    if (!aborted) {
      aborted = true
      clearTimeout(timeoutId)
      controller.abort()
    }
  }

  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutId)
      onExternalAbort()
      onError('分析已取消')
      return
    }
    signal.addEventListener('abort', onExternalAbort)
  }

  const cleanup = () => {
    clearTimeout(timeoutId)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }

  let response: Response
  try {
    response = await fetch('/api/analysis/batch-quick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stocks }),
      signal: controller.signal,
    })
  } catch (e: any) {
    cleanup()
    if (e.name === 'AbortError') {
      onError(aborted && signal?.aborted ? '分析已取消' : '请求超时')
    } else {
      onError(`请求失败: ${e.message}`)
    }
    return
  }

  if (!response.ok) {
    cleanup()
    onError(`HTTP ${response.status}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    cleanup()
    onError('No response body')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''

  const resetStreamTimeout = () => {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      if (!aborted) {
        aborted = true
        controller.abort()
        onError('流读取超时')
      }
    }, SSE_TIMEOUT_MS)
  }
  resetStreamTimeout()

  try {
    while (true) {
      if (controller.signal.aborted) {
        reader.cancel()
        onError('分析已取消')
        return
      }

      const { done, value } = await reader.read()
      if (done) break

      resetStreamTimeout()
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          try {
            const sanitizedStr = dataStr
              .replace(/:\s*NaN\s*([,}])/g, ': null$1')
              .replace(/:\s*Infinity\s*([,}])/g, ': null$1')
              .replace(/:\s*-Infinity\s*([,}])/g, ': null$1')
            const data = JSON.parse(sanitizedStr)
            if (currentEvent === 'progress') {
              onProgress(data)
            } else if (currentEvent === 'complete') {
              onComplete(data)
              cleanup()
              reader.cancel().catch(() => {})
              return
            }
          } catch (parseErr) {
            console.warn('SSE parse error:', parseErr)
          }
          currentEvent = ''
        }
      }
    }
    cleanup()
  } catch (e: any) {
    cleanup()
    if (e.name === 'AbortError') {
      onError('分析已取消')
    } else {
      onError(`流读取错误: ${e.message}`)
    }
  }
}
