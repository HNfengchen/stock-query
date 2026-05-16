<script setup lang="ts">
import { computed } from 'vue'
import type { MarketStatus } from '@/types'

const props = defineProps<{ status: MarketStatus }>()

const indexChangeType = computed(() => {
  const v = props.status.indexChange
  if (v === null) return 'info'
  if (v > 0) return 'success'
  if (v < 0) return 'danger'
  return 'warning'
})

const indexChangeText = computed(() => {
  const v = props.status.indexChange
  if (v === null) return '-'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
})

const sentimentType = computed(() => {
  const s = props.status.sentiment
  if (s === '乐观') return 'success'
  if (s === '悲观') return 'danger'
  return 'warning'
})

const volatilityType = computed(() => {
  const v = props.status.volatilityState
  if (v === '低波动') return 'success'
  if (v === '高波动') return 'danger'
  return 'warning'
})

const riskType = computed(() => {
  const r = props.status.riskLevel
  if (r === '低风险') return 'success'
  if (r === '高风险') return 'danger'
  return 'warning'
})

const hmmType = computed(() => {
  const s = props.status.hmmState
  if (!s) return 'info'
  if (s.includes('牛') || s.includes('上涨') || s.includes('trend')) return 'success'
  if (s.includes('熊') || s.includes('下跌')) return 'danger'
  return 'warning'
})

const hmmLabel = computed(() => {
  const s = props.status.hmmState
  if (!s) return '未启用'
  const map: Record<string, string> = {
    bull_trend: '牛市趋势',
    bear_trend: '熊市趋势',
    bull_volatile: '牛市震荡',
    bear_volatile: '熊市震荡',
    range: '区间震荡',
    volatile: '高波动',
  }
  return map[s] || s
})
</script>

<template>
  <div class="market-status-panel">
    <div class="panel-title">市场环境</div>

    <div class="status-list">
      <div class="status-item">
        <span class="status-label">大盘状态</span>
        <el-tag :type="indexChangeType" size="small" effect="dark">
          {{ indexChangeText }}
        </el-tag>
      </div>

      <div class="status-item">
        <span class="status-label">市场情绪</span>
        <el-tag :type="sentimentType" size="small" effect="dark">
          {{ status.sentiment }}
        </el-tag>
      </div>

      <div class="status-item">
        <span class="status-label">波动率</span>
        <el-tag :type="volatilityType" size="small" effect="dark">
          {{ status.volatilityState }}
        </el-tag>
      </div>

      <div class="status-item">
        <span class="status-label">风险等级</span>
        <el-tag :type="riskType" size="small" effect="dark">
          {{ status.riskLevel }}
        </el-tag>
      </div>

      <div class="status-item">
        <span class="status-label">HMM状态</span>
        <el-tag :type="hmmType" size="small" effect="dark">
          {{ hmmLabel }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.market-status-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: var(--transition-base);
}

.market-status-panel:hover {
  border-color: var(--border-active);
}

.panel-title {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.status-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}
</style>
