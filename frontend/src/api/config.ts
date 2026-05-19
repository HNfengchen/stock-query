export const parseEnvInt = (value: string | undefined, defaultValue: number): number => {
  if (value === undefined) return defaultValue
  const parsed = parseInt(value, 10)
  return isNaN(parsed) ? defaultValue : parsed
}

export const API_TIMEOUTS = {
  default: parseEnvInt(import.meta.env.VITE_API_TIMEOUT_DEFAULT, 30000),
  analysis: parseEnvInt(import.meta.env.VITE_API_TIMEOUT_ANALYSIS, 120000),
  sse: parseEnvInt(import.meta.env.VITE_API_TIMEOUT_SSE, 180000),
  backtest: parseEnvInt(import.meta.env.VITE_API_TIMEOUT_BACKTEST, 300000),
} as const
