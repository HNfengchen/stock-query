import axios from 'axios'
import type { AnalysisRequest, AnalysisResult, BatchAnalysisRequest, BatchAnalysisResult, BatchQuickSummary, AnalysisStage } from '@/types'

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

const SSE_TIMEOUT_MS = 600000

export async function batchQuickAnalyzeStream(
  stocks: AnalysisRequest[],
  onProgress: (event: QuickProgressEvent) => void,
  onComplete: (event: QuickCompleteEvent) => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), SSE_TIMEOUT_MS)

  let aborted = false

  const onExternalAbort = () => {
    if (!aborted) {
      aborted = true
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

  let response: Response
  try {
    response = await fetch('/api/analysis/batch-quick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stocks }),
      signal: controller.signal,
    })
  } catch (e: any) {
    clearTimeout(timeoutId)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
    if (e.name === 'AbortError') {
      onError(aborted && signal?.aborted ? '分析已取消' : '请求超时')
    } else {
      onError(`请求失败: ${e.message}`)
    }
    return
  }

  clearTimeout(timeoutId)
  if (signal) signal.removeEventListener('abort', onExternalAbort)

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

  try {
    while (true) {
      if (controller.signal.aborted) {
        reader.cancel()
        onError('分析已取消')
        return
      }

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
          } catch (parseErr) {
            console.warn('SSE parse error:', parseErr)
          }
          currentEvent = ''
        }
      }
    }
  } catch (e: any) {
    if (e.name === 'AbortError') {
      onError('分析已取消')
    } else {
      onError(`流读取错误: ${e.message}`)
    }
  }
}

export interface StageCallbacks {
  onBasic?: (data: any) => void
  onTechnical?: (data: any) => void
  onRisk?: (data: any) => void
  onPrediction?: (data: any) => void
  onComplete?: (data: AnalysisResult) => void
  onError?: (error: string) => void
}

export function analyzeStockStream(
  stockInput: string,
  positionStatus: string = '未持有',
  costPrice?: number | null,
  callbacks: StageCallbacks = {},
): AbortController {
  const controller = new AbortController()
  const params = new URLSearchParams({ stock_input: stockInput, position_status: positionStatus })
  if (costPrice != null) {
    params.set('cost_price', String(costPrice))
  }

  const stageCallbackMap: Record<string, (data: any) => void> = {
    stage_basic: callbacks.onBasic || (() => {}),
    stage_technical: callbacks.onTechnical || (() => {}),
    stage_risk: callbacks.onRisk || (() => {}),
    stage_prediction: callbacks.onPrediction || (() => {}),
  }

  fetch(`/api/analysis/stream?${params.toString()}`, { signal: controller.signal })
    .then((response) => {
      if (!response.ok) {
        callbacks.onError?.(`HTTP ${response.status}`)
        return
      }
      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError?.('No response body')
        return
      }
      const decoder = new TextDecoder()
      let buffer = ''

      const processChunk = (): Promise<void> => {
        return reader.read().then(({ done, value }) => {
          if (done) return

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
                if (currentEvent === 'stage_complete') {
                  callbacks.onComplete?.(data)
                } else if (currentEvent === 'error') {
                  callbacks.onError?.(data.error || '分析失败')
                } else if (currentEvent === 'heartbeat') {
                  // ignore
                } else if (currentEvent && stageCallbackMap[currentEvent]) {
                  stageCallbackMap[currentEvent](data)
                }
              } catch {
                // ignore parse errors
              }
              currentEvent = ''
            }
          }

          return processChunk()
        })
      }

      return processChunk()
    })
    .catch((e: any) => {
      if (e.name !== 'AbortError') {
        callbacks.onError?.(`请求失败: ${e.message}`)
      }
    })

  return controller
}

export function createProgressWebSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${protocol}//${host}/ws/progress/${taskId}`)
}
