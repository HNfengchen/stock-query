import { ref } from 'vue'

export interface SSEEvent {
  event: string
  data: unknown
}

export interface SSEStreamOptions {
  url: string
  timeout?: number
  signal?: AbortSignal
  onEvent: (event: SSEEvent) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}

export function connectSSEStream(options: SSEStreamOptions): Promise<void> {
  const {
    url,
    timeout = 180000,
    signal: externalSignal,
    onEvent,
    onError,
    onComplete,
  } = options

  return new Promise<void>((resolve, reject) => {
    const controller = new AbortController()
    const combinedSignal = controller.signal

    if (externalSignal) {
      externalSignal.addEventListener('abort', () => {
        controller.abort()
      }, { once: true })
    }

    let timeoutId: ReturnType<typeof setTimeout>
    const resetTimeout = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        controller.abort()
        reject(new Error('SSE stream timeout'))
      }, timeout)
    }
    resetTimeout()

    fetch(url, { signal: combinedSignal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = ''

        const processChunk = (): Promise<void> => {
          return reader.read().then(({ done, value }) => {
            if (done) {
              clearTimeout(timeoutId)
              if (onComplete) onComplete()
              resolve()
              return
            }
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            let hasActivity = false
            for (const line of lines) {
              if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim()
                hasActivity = true
              } else if (line.startsWith('data: ')) {
                const dataStr = line.slice(6)
                hasActivity = true
                try {
                  const eventData = JSON.parse(dataStr)
                  onEvent({ event: currentEvent, data: eventData })
                } catch (e) {
                  console.debug('[SSE] parse error:', e)
                }
                currentEvent = ''
              }
            }
            if (hasActivity) {
              resetTimeout()
            }
            return processChunk()
          }).catch((e: unknown) => {
            clearTimeout(timeoutId)
            if (e instanceof DOMException && e.name === 'AbortError') {
              resolve()
            } else {
              const error = e instanceof Error ? e : new Error(String(e))
              if (onError) onError(error)
              reject(error)
            }
          })
        }

        return processChunk()
      })
      .catch((e: unknown) => {
        clearTimeout(timeoutId)
        const error = e instanceof Error ? e : new Error(String(e))
        if (onError) onError(error)
        reject(error)
      })
  })
}
