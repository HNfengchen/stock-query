import { getLogger } from './core'

const logger = getLogger('error')

export function setupErrorCapture(): () => void {
  const originalOnError = window.onerror
  const originalUnhandledRejection = window.onunhandledrejection

  window.onerror = (message, source, lineno, colno, error) => {
    logger.error('JavaScript Runtime Error', error, {
      message: String(message),
      source: source || '',
      lineno,
      colno,
    })

    if (originalOnError) {
      return originalOnError(message, source, lineno, colno, error)
    }
    return false
  }

  window.onunhandledrejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason
    logger.error('Unhandled Promise Rejection', reason instanceof Error ? reason : undefined, {
      reason: reason instanceof Error ? reason.message : String(reason),
    })

    if (originalUnhandledRejection) {
      originalUnhandledRejection.call(window, event)
    }
  }

  const resourceErrorHandler = (event: Event) => {
    const target = event.target as HTMLElement
    if (!target) return

    const tagName = target.tagName?.toLowerCase()
    if (tagName === 'img' || tagName === 'script' || tagName === 'link' || tagName === 'video' || tagName === 'audio') {
      const src = (target as HTMLImageElement).src || (target as HTMLLinkElement).href || ''
      logger.warn('Resource Load Failed', {
        tag: tagName,
        src,
        type: 'resource_error',
      })
    }
  }

  document.addEventListener('error', resourceErrorHandler, true)

  return () => {
    window.onerror = originalOnError
    window.onunhandledrejection = originalUnhandledRejection
    document.removeEventListener('error', resourceErrorHandler, true)
  }
}
