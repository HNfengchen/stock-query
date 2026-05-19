import { getLogger } from './core'

const logger = getLogger('performance')

export function setupPerformanceLogging(): () => void {
  if (typeof window === 'undefined' || !window.performance) return () => {}

  logPageLoadTiming()
  logResourceTiming()

  const observer = observeLongTasks()
  const paintObserver = observePaintTiming()

  return () => {
    observer?.disconnect()
    paintObserver?.disconnect()
  }
}

function logPageLoadTiming(): void {
  const logTiming = () => {
    try {
      const [nav] = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[]
      if (!nav) return

      logger.info('Page Load', {
        category: 'performance',
        dns: Math.round(nav.domainLookupEnd - nav.domainLookupStart),
        tcp: Math.round(nav.connectEnd - nav.connectStart),
        ssl: nav.secureConnectionStart > 0 ? Math.round(nav.connectEnd - nav.secureConnectionStart) : 0,
        ttfb: Math.round(nav.responseStart - nav.requestStart),
        download: Math.round(nav.responseEnd - nav.responseStart),
        domParse: Math.round(nav.domInteractive - nav.responseEnd),
        domReady: Math.round(nav.domContentLoadedEventEnd - nav.fetchStart),
        loadComplete: Math.round(nav.loadEventEnd - nav.fetchStart),
        transferSize: nav.transferSize,
      })
    } catch {}
  }

  if (document.readyState === 'complete') {
    setTimeout(logTiming, 0)
  } else {
    window.addEventListener('load', () => setTimeout(logTiming, 100))
  }
}

function logResourceTiming(): void {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const resource = entry as PerformanceResourceTiming
        if (resource.initiatorType === 'xmlhttprequest' || resource.initiatorType === 'fetch') {
          const duration = Math.round(resource.duration)
          if (duration > 3000) {
            logger.warn('Slow API Request', {
              category: 'performance',
              url: resource.name,
              duration,
              transferSize: resource.transferSize,
              initiatorType: resource.initiatorType,
            })
          } else {
            logger.debug('API Request Timing', {
              category: 'performance',
              url: resource.name,
              duration,
              transferSize: resource.transferSize,
            })
          }
        }
      }
    })
    observer.observe({ type: 'resource', buffered: true })
  } catch {}
}

function observeLongTasks(): PerformanceObserver | null {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        logger.warn('Long Task Detected', {
          category: 'performance',
          duration: Math.round(entry.duration),
          startTime: Math.round(entry.startTime),
          name: entry.name,
        })
      }
    })
    observer.observe({ type: 'longtask', buffered: true })
    return observer
  } catch {
    return null
  }
}

function observePaintTiming(): PerformanceObserver | null {
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        logger.info('Paint Timing', {
          category: 'performance',
          name: entry.name,
          startTime: Math.round(entry.startTime),
        })
      }
    })
    observer.observe({ type: 'paint', buffered: true })
    return observer
  } catch {
    return null
  }
}

export function logApiTiming(method: string, url: string, durationMs: number, status: number): void {
  const data = {
    category: 'performance',
    method,
    url,
    duration_ms: durationMs,
    status,
  }

  if (durationMs > 5000) {
    logger.warn('Slow API Response', data)
  } else if (durationMs > 2000) {
    logger.info('API Response (Slow)', data)
  } else {
    logger.debug('API Response', data)
  }
}
