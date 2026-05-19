export function generateTraceId(): string {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).slice(2, 10)
  const random2 = Math.random().toString(36).slice(2, 6)
  return `${timestamp}-${random}-${random2}`
}

const TRACE_ID_KEY = '__trace_id'
const TRACE_ID_HEADER = 'X-Trace-Id'

export function getTraceId(): string {
  let traceId = sessionStorage.getItem(TRACE_ID_KEY)
  if (!traceId) {
    traceId = generateTraceId()
    sessionStorage.setItem(TRACE_ID_KEY, traceId)
  }
  return traceId
}

export function setTraceId(traceId: string): void {
  sessionStorage.setItem(TRACE_ID_KEY, traceId)
}

export function getTraceIdHeaderName(): string {
  return TRACE_ID_HEADER
}

export function extractTraceIdFromResponse(response: Response | { headers?: { get?: (name: string) => string | null } }): string | null {
  try {
    if ('headers' in response && response.headers && typeof response.headers.get === 'function') {
      return response.headers.get(TRACE_ID_HEADER)
    }
  } catch {}
  return null
}
