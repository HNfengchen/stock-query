import { Logger, getLogger } from './core'
import { setupErrorCapture } from './error-capture'
import { setupPerformanceLogging, logApiTiming } from './performance'
import { setupBehaviorLogging, logPageView, logUserAction } from './behavior'
import { getTraceId, setTraceId, getTraceIdHeaderName, extractTraceIdFromResponse } from './trace'
import type { LoggerConfig } from './core'

export { Logger, getLogger } from './core'
export { LogLevel, LOG_LEVEL_NAMES, parseLogLevel } from './levels'
export { getTraceId, setTraceId } from './trace'
export { logApiTiming } from './performance'
export { logPageView, logUserAction } from './behavior'
export { sanitizeData } from './sensitive'

export interface LoggingSystemConfig extends LoggerConfig {
  enableErrorCapture?: boolean
  enablePerformance?: boolean
  enableBehavior?: boolean
}

const CLEANUP_FNS: (() => void)[] = []

export function initLogging(config: LoggingSystemConfig = {}): Logger {
  const {
    enableErrorCapture = true,
    enablePerformance = true,
    enableBehavior = true,
    ...loggerConfig
  } = config

  const logger = Logger.init(loggerConfig)

  if (enableErrorCapture) {
    const cleanup = setupErrorCapture()
    CLEANUP_FNS.push(cleanup)
  }

  if (enablePerformance) {
    const cleanup = setupPerformanceLogging()
    CLEANUP_FNS.push(cleanup)
  }

  if (enableBehavior) {
    const cleanup = setupBehaviorLogging()
    CLEANUP_FNS.push(cleanup)
  }

  return logger
}

export function destroyLogging(): void {
  for (const fn of CLEANUP_FNS) {
    try { fn() } catch {}
  }
  CLEANUP_FNS.length = 0
}

export function setupAxiosInterceptors(axiosInstance: {
  interceptors: {
    request: { use: (fn: (config: any) => any) => number }
    response: { use: (fn: (response: any) => any, fn2: (error: any) => any) => number }
  }
}): void {
  const logger = getLogger('http')

  axiosInstance.interceptors.request.use((config: any) => {
    config.headers = config.headers || {}
    config.headers[getTraceIdHeaderName()] = getTraceId()
    config._startTime = Date.now()
    return config
  })

  axiosInstance.interceptors.response.use(
    (response: any) => {
      const duration = Date.now() - (response.config?._startTime || Date.now())
      const method = (response.config?.method || 'unknown').toUpperCase()
      const url = response.config?.url || ''
      const status = response.status

      logApiTiming(method, url, duration, status)

      const serverTraceId = extractTraceIdFromResponse(response)
      if (serverTraceId) {
        setTraceId(serverTraceId)
      }

      return response
    },
    (error: any) => {
      const duration = Date.now() - (error.config?._startTime || Date.now())
      const method = (error.config?.method || 'unknown').toUpperCase()
      const url = error.config?.url || ''
      const status = error.response?.status || 0

      logApiTiming(method, url, duration, status)

      logger.error('API Request Failed', error, {
        method,
        url,
        status,
        duration_ms: duration,
        message: error.message,
        code: error.code,
      })

      return Promise.reject(error)
    },
  )
}
