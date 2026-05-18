import { describe, it, expect } from 'vitest'
import { API_TIMEOUTS, parseEnvInt } from '../config'

describe('parseEnvInt', () => {
  it('returns default value when input is undefined', () => {
    expect(parseEnvInt(undefined, 30000)).toBe(30000)
  })

  it('parses valid numeric string', () => {
    expect(parseEnvInt('5000', 30000)).toBe(5000)
  })

  it('falls back to default when input is not a valid number', () => {
    expect(parseEnvInt('abc', 30000)).toBe(30000)
  })

  it('falls back to default when input is empty string', () => {
    expect(parseEnvInt('', 30000)).toBe(30000)
  })

  it('parses large numeric strings', () => {
    expect(parseEnvInt('600000', 300000)).toBe(600000)
  })

  it('truncates decimal values', () => {
    expect(parseEnvInt('30.5', 30000)).toBe(30)
  })

  it('handles negative numbers', () => {
    expect(parseEnvInt('-1', 30000)).toBe(-1)
  })

  it('ignores leading/trailing whitespace in numeric strings', () => {
    expect(parseEnvInt('  5000  ', 30000)).toBe(5000)
  })
})

describe('API_TIMEOUTS', () => {
  it('has expected default values', () => {
    expect(API_TIMEOUTS.default).toBe(30000)
    expect(API_TIMEOUTS.analysis).toBe(120000)
    expect(API_TIMEOUTS.sse).toBe(600000)
    expect(API_TIMEOUTS.backtest).toBe(300000)
  })

  it('has all required keys', () => {
    const keys = Object.keys(API_TIMEOUTS)
    expect(keys).toEqual(['default', 'analysis', 'sse', 'backtest'])
  })

  it('all values are positive numbers', () => {
    const values = Object.values(API_TIMEOUTS)
    values.forEach(v => {
      expect(v).toBeGreaterThan(0)
    })
  })

  it('analysis timeout is greater than default', () => {
    expect(API_TIMEOUTS.analysis).toBeGreaterThan(API_TIMEOUTS.default)
  })

  it('sse timeout is greater than analysis timeout', () => {
    expect(API_TIMEOUTS.sse).toBeGreaterThan(API_TIMEOUTS.analysis)
  })

  it('backtest timeout is greater than default', () => {
    expect(API_TIMEOUTS.backtest).toBeGreaterThan(API_TIMEOUTS.default)
  })
})
