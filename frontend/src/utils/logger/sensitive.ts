const SENSITIVE_KEYS = new Set([
  'password', 'passwd', 'pwd', 'secret', 'token', 'access_token',
  'refresh_token', 'api_key', 'apikey', 'private_key', 'credit_card',
  'card_number', 'cvv', 'ssn', 'id_card', 'bank_card', 'authorization',
  'cookie',
])

const MASK = '******'

const PHONE_RE = /1[3-9]\d{9}/g
const ID_CARD_RE = /[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]/g
const BANK_CARD_RE = /\b\d{16,19}\b/g
const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g

function maskStringPatterns(value: string): string {
  if (typeof value !== 'string') return value
  value = value.replace(PHONE_RE, m => m.slice(0, 3) + MASK + m.slice(-2))
  value = value.replace(ID_CARD_RE, m => m.slice(0, 3) + MASK + m.slice(-1))
  value = value.replace(BANK_CARD_RE, m => m.slice(0, 4) + MASK + m.slice(-4))
  value = value.replace(EMAIL_RE, m => {
    const parts = m.split('@')
    return parts[0].slice(0, 2) + MASK + '@' + parts[1]
  })
  return value
}

export function sanitizeData(data: unknown, depth = 0): unknown {
  if (depth > 10) return '...'
  if (data === null || data === undefined) return data
  if (typeof data === 'boolean') return data
  if (typeof data === 'number') return data
  if (typeof data === 'string') return maskStringPatterns(data)
  if (Array.isArray(data)) return data.map(item => sanitizeData(item, depth + 1))
  if (typeof data === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const keyLower = key.toLowerCase()
      if (SENSITIVE_KEYS.has(keyLower)) {
        result[key] = MASK
      } else if (typeof value === 'string') {
        result[key] = maskStringPatterns(value)
      } else {
        result[key] = sanitizeData(value, depth + 1)
      }
    }
    return result
  }
  return String(data)
}
