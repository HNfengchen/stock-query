import axios from 'axios'
import { API_TIMEOUTS } from './config'
import { setupAxiosInterceptors } from '@/utils/logger'

const api = axios.create({
  baseURL: '',
  timeout: API_TIMEOUTS.default,
})

setupAxiosInterceptors(api)

// 训练模式
export type TrainingMode = 'incremental' | 'force' | 'hmm_only'

// 模型信息
export interface ModelInfo {
  stock_code: string
  trained_at: string
  n_features: number
  feature_names?: string[]
}

// HMM模型信息
export interface HmmInfo {
  exists: boolean
  trained_at: string | null
}

// 训练状态
export interface TrainingStatus {
  running: boolean
  mode: string | null
  started_at: string | null
  pid: number | null
}

const SSE_TIMEOUT_MS = 10 * 60 * 1000 // 10分钟

// 启动训练（返回SSE流）
export async function startTrainingStream(
  mode: TrainingMode,
  onLog: (msg: string, level: string) => void,
  onProgress: (stock: string, status: string) => void,
  onComplete: (summary: { success_count: number; failed_count: number; skipped_count: number }) => void,
  onError: (msg: string) => void,
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
      onError('训练已取消')
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
    response = await fetch('/api/training/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
      signal: controller.signal,
    })
  } catch (e: any) {
    cleanup()
    if (e.name === 'AbortError') {
      onError(aborted && signal?.aborted ? '训练已取消' : '请求超时')
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
        onError('训练已取消')
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
            const data = JSON.parse(dataStr)
            if (currentEvent === 'log') {
              onLog(data.message || data.msg || dataStr, data.level || 'info')
            } else if (currentEvent === 'progress') {
              onProgress(data.stock, data.status)
            } else if (currentEvent === 'complete') {
              onComplete(data)
              cleanup()
              reader.cancel().catch(() => {})
              return
            }
          } catch {
            onLog(dataStr, 'info')
          }
          currentEvent = ''
        }
      }
    }
    cleanup()
  } catch (e: any) {
    cleanup()
    if (e.name === 'AbortError') {
      onError('训练已取消')
    } else {
      onError(`流读取错误: ${e.message}`)
    }
  }
}

// 查询训练状态
export async function getTrainingStatus(): Promise<TrainingStatus> {
  const response = await api.get('/api/training/status')
  return response.data
}

// 获取模型列表
export async function getModels(): Promise<{ models: ModelInfo[]; hmm: HmmInfo; total: number }> {
  const response = await api.get('/api/training/models')
  return response.data
}

// 删除模型
export async function deleteModel(stockCode: string): Promise<void> {
  await api.delete(`/api/training/models/${stockCode}`)
}
