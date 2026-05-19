import { LogLevel, LOG_LEVEL_NAMES, parseLogLevel } from './levels'
import { sanitizeData } from './sensitive'
import { getTraceId } from './trace'
import type { Transport, LogEntry } from './transport'
import { ConsoleTransport, LocalStorageTransport, RemoteTransport } from './transport'

export interface LoggerConfig {
  level?: string
  service?: string
  module?: string
  transports?: Transport[]
  remoteEndpoint?: string
  enableLocalStorage?: boolean
}

const DEFAULT_CONFIG: Required<Omit<LoggerConfig, 'remoteEndpoint'>> = {
  level: 'INFO',
  service: 'stock-query-frontend',
  module: 'app',
  transports: [],
  enableLocalStorage: true,
}

export class Logger {
  private level: LogLevel
  private service: string
  private module: string
  private transports: Transport[] = []
  private static instance: Logger | null = null

  constructor(config: LoggerConfig = {}) {
    const merged = { ...DEFAULT_CONFIG, ...config }
    this.level = parseLogLevel(merged.level)
    this.service = merged.service
    this.module = merged.module

    this.transports = [...merged.transports]

    if (!this.transports.some(t => t instanceof ConsoleTransport)) {
      this.transports.push(new ConsoleTransport())
    }

    if (merged.enableLocalStorage && !this.transports.some(t => t instanceof LocalStorageTransport)) {
      this.transports.push(new LocalStorageTransport())
    }

    if (merged.remoteEndpoint && !this.transports.some(t => t instanceof RemoteTransport)) {
      const remote = new RemoteTransport({ endpoint: merged.remoteEndpoint })
      remote.start()
      this.transports.push(remote)
    }
  }

  static init(config: LoggerConfig = {}): Logger {
    Logger.instance = new Logger(config)
    return Logger.instance
  }

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger()
    }
    return Logger.instance
  }

  setLevel(level: string): void {
    this.level = parseLogLevel(level)
  }

  getLevel(): LogLevel {
    return this.level
  }

  child(module: string): Logger {
    const childLogger = new Logger({
      level: LOG_LEVEL_NAMES[this.level],
      service: this.service,
      module: `${this.module}.${module}`,
      transports: this.transports,
      enableLocalStorage: false,
    })
    return childLogger
  }

  debug(message: string, data?: unknown): void {
    this.log(LogLevel.DEBUG, message, data)
  }

  info(message: string, data?: unknown): void {
    this.log(LogLevel.INFO, message, data)
  }

  warn(message: string, data?: unknown): void {
    this.log(LogLevel.WARN, message, data)
  }

  error(message: string, error?: Error | unknown, data?: unknown): void {
    const entry = this.createEntry(LogLevel.ERROR, message, data)
    if (error instanceof Error) {
      entry.error = {
        type: error.name,
        message: error.message,
        stack: error.stack,
      }
    } else if (error !== undefined) {
      entry.error = {
        type: 'Unknown',
        message: String(error),
      }
    }
    this.writeEntry(entry)
  }

  private log(level: LogLevel, message: string, data?: unknown): void {
    if (level < this.level) return
    const entry = this.createEntry(level, message, data)
    this.writeEntry(entry)
  }

  private createEntry(level: LogLevel, message: string, data?: unknown): LogEntry {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level: LOG_LEVEL_NAMES[level],
      service: this.service,
      module: this.module,
      trace_id: getTraceId(),
      message,
    }
    if (data !== undefined) {
      entry.data = sanitizeData(data)
    }
    return entry
  }

  private writeEntry(entry: LogEntry): void {
    for (const transport of this.transports) {
      try {
        transport.log(entry)
      } catch {
        // transport failure should not break the app
      }
    }
  }

  async flush(): Promise<void> {
    await Promise.all(
      this.transports.map(t => t.flush?.() ?? Promise.resolve())
    )
  }
}

export function getLogger(module?: string): Logger {
  const root = Logger.getInstance()
  return module ? root.child(module) : root
}
