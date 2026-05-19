import { getLogger } from './core'

const logger = getLogger('behavior')

interface BehaviorEvent {
  category: string
  action: string
  element_id?: string
  element_tag?: string
  element_text?: string
  page_url?: string
  timestamp: string
  data?: unknown
}

function createBehaviorEvent(
  action: string,
  extra?: Partial<BehaviorEvent>,
): BehaviorEvent {
  return {
    category: 'behavior',
    action,
    element_id: extra?.element_id,
    element_tag: extra?.element_tag,
    element_text: extra?.element_text,
    page_url: window.location.href,
    timestamp: new Date().toISOString(),
    data: extra?.data,
  }
}

export function setupBehaviorLogging(): () => void {
  const clickHandler = (event: MouseEvent) => {
    const target = event.target as HTMLElement
    if (!target) return

    const elementId = target.id || target.getAttribute('data-log-id') || ''
    const elementTag = target.tagName?.toLowerCase() || ''
    const elementText = getElementText(target)

    if (shouldIgnoreElement(target)) return

    logger.info('User Click', createBehaviorEvent('click', {
      element_id: elementId,
      element_tag: elementTag,
      element_text: truncate(elementText, 100),
    }))
  }

  const submitHandler = (event: SubmitEvent) => {
    const form = event.target as HTMLFormElement
    if (!form) return

    logger.info('Form Submit', createBehaviorEvent('form_submit', {
      element_id: form.id || '',
      element_tag: 'form',
      element_text: form.action || '',
    }))
  }

  document.addEventListener('click', clickHandler, true)
  document.addEventListener('submit', submitHandler, true)

  return () => {
    document.removeEventListener('click', clickHandler, true)
    document.removeEventListener('submit', submitHandler, true)
  }
}

export function logPageView(path?: string, name?: string): void {
  logger.info('Page View', createBehaviorEvent('page_view', {
    data: {
      path: path || window.location.pathname,
      name: name || '',
      referrer: document.referrer,
    },
  }))
}

export function logUserAction(action: string, data?: unknown): void {
  logger.info('User Action', createBehaviorEvent(action, {
    data,
  }))
}

function getElementText(el: HTMLElement): string {
  if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
    return ''
  }
  const text = el.textContent?.trim() || el.getAttribute('aria-label') || el.getAttribute('title') || ''
  return text
}

function shouldIgnoreElement(el: HTMLElement): boolean {
  if (el.closest('[data-log-ignore]')) return true
  const tag = el.tagName?.toLowerCase()
  return tag === 'svg' || tag === 'path' || tag === 'use'
}

function truncate(str: string, maxLen: number): string {
  if (!str || str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}
