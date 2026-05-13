export const TREND_LABEL_MAP: Record<string, string> = {
  strong_up: '大幅上涨',
  up: '上涨',
  neutral: '震荡',
  down: '下跌',
  strong_down: '大幅下跌',
}

export function getTrendColor(trend: string): string {
  if (trend === 'strong_up') return 'var(--color-up-strong, #00897b)'
  if (trend === 'up') return 'var(--color-up)'
  if (trend === 'strong_down') return 'var(--color-down-strong, #c62828)'
  if (trend === 'down') return 'var(--color-down)'
  return 'var(--text-muted)'
}

export function getTrendTagType(trend: string): string {
  if (trend === 'strong_up' || trend === 'up') return 'success'
  if (trend === 'strong_down' || trend === 'down') return 'danger'
  return 'warning'
}

export function getTrendClass(trend: string): string {
  if (trend === 'strong_up') return 'trend-strong-up'
  if (trend === 'strong_down') return 'trend-strong-down'
  return ''
}

export function trendToValue(trend: string): number {
  if (trend === 'strong_up') return 2
  if (trend === 'up') return 1
  if (trend === 'down') return -1
  if (trend === 'strong_down') return -2
  return 0
}

export function changeToTrendValue(change: number): number {
  if (change > 0.03) return 2
  if (change > 0.01) return 1
  if (change < -0.03) return -2
  if (change < -0.01) return -1
  return 0
}

export function fmtNum(val: any, decimals: number = 2): string {
  if (val === null || val === undefined || val === 'N/A') return '-'
  const n = Number(val)
  if (isNaN(n)) return '-'
  return n.toFixed(decimals)
}

export function fmtMarketCap(val: any): string {
  if (val === null || val === undefined || val === 'N/A') return '-'
  const n = Number(val)
  if (isNaN(n)) return '-'
  if (n >= 1e12) return (n / 1e12).toFixed(2) + '万亿'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(2)
}

export function fmtVolume(val: any): string {
  if (val === null || val === undefined || val === 'N/A') return '-'
  const n = Number(val)
  if (isNaN(n)) return '-'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}

export function fmtAmount(value: number): string {
  if (Math.abs(value) >= 1e8) return (value / 1e8).toFixed(2) + '亿'
  if (Math.abs(value) >= 1e4) return (value / 1e4).toFixed(2) + '万'
  return value.toFixed(0)
}
