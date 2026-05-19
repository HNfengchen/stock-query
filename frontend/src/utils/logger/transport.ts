import type { LogLevel } from './levels'
import { LOG_LEVEL_NAMES } from './levels'
import { sanitizeData } from './sensitive'
import { getTraceId } from './trace'

export interface LogEntry {
  timestamp: string
  level: string
  service: string
  module: string
  trace_id: string
  message: string
  category?: string
  data?: unknown
  error?: {
    type: string
    message: string
    stack?: string
  }
  environment?: Record<string, unknown>
}

export interface Transport {
  name: string
  log(entry: LogEntry): void | Promise<void>
  flush?(): Promise<void>
}

export class ConsoleTransport implements Transport {
  name = 'console'

  log(entry: LogEntry): void {
    const levelNum = Object.entries(LOG_LEVEL_NAMES).find(([, v]) => v === entry.level)?.[0]
    const traceStr = entry.trace_id ? ` [${entry.trace_id.slice(0, 8)}]` : ''
    const categoryStr = entry.category ? ` <${entry.category}>` : ''
    const prefix = `${entry.level} ${entry.timestamp} ${entry.module}${traceStr}${categoryStr}`

    const fn = levelNum === '3' ? console.error : levelNum === '2' ? console.warn : levelNum === '0' ? console.debug : console.info

    if (entry.error) {
      fn(prefix, entry.message, entry.error, entry.data ?? '')
    } else if (entry.data !== undefined) {
      fn(prefix, entry.message, entry.data)
    } else {
      fn(prefix, entry.message)
    }
  }
}

const LOCAL_STORAGE_KEY = '__app_logs'
const MAX_LOCAL_ENTRIES = 500

export class LocalStorageTransport implements Transport {
  name = 'localStorage'
  private key: string
  private maxEntries: number

  constructor(key = LOCAL_STORAGE_KEY, maxEntries = MAX_LOCAL_ENTRIES) {
    this.key = key
    this.maxEntries = maxEntries
  }

  log(entry: LogEntry): void {
    try {
      const stored = this.getEntries()
      stored.push(entry)
      while (stored.length > this.maxEntries) {
        stored.shift()
      }
      localStorage.setItem(this.key, JSON.stringify(stored))
    } catch {
      // localStorage full or unavailable, silently ignore
    }
  }

  getEntries(): LogEntry[] {
    try {
      const raw = localStorage.getItem(this.key)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }

  clear(): void {
    try {
      localStorage.removeItem(this.key)
    } catch {}
  }

  flush(): Promise<void> {
    return Promise.resolve()
  }
}

interface RemoteTransportOptions {
  endpoint: string
  batchSize?: number
  flushInterval?: number
}

export class RemoteTransport implements Transport {
  name = 'remote'
  private endpoint: string
  private batchSize: number
  private flushInterval: number
  private buffer: LogEntry[] = []
  private timer: ReturnType<typeof setInterval> | null = null
  private isFlushing = false

  constructor(options: RemoteTransportOptions) {
    this.endpoint = options.endpoint
    this.batchSize = options.batchSize ?? 20
    this.flushInterval = options.flushInterval ?? 5000
  }

  log(entry: LogEntry): void {
    this.buffer.push(entry)
    if (this.buffer.length >= this.batchSize) {
      this.flush()
    }
  }

  start(): void {
    if (this.timer) return
    this.timer = setInterval(() => {
      if (this.buffer.length > 0) {
        this.flush()
      }
    }, this.flushInterval)
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  async flush(): Promise<void> {
    if (this.isFlushing || this.buffer.length === 0) return
    this.isFlushing = true

    const batch = this.buffer.splice(0, this.batchSize)
    try {
      const sanitized = sanitizeData(batch)
      if (navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify(sanitized)], { type: 'application/json' })
        navigator.sendBeacon(this.endpoint, blob)
      } else {
        await fetch(this.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(sanitized),
          keepalive: true,
        })
      }
    } catch {
      this.buffer.unshift(...batch)
    } finally {
      this.isFlushing = false
    }
  }
}
