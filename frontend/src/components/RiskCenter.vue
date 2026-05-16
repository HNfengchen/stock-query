<script setup lang="ts">
import { computed } from 'vue'
import type { RiskAssessment } from '@/types'

const props = defineProps<{ risk: RiskAssessment }>()

function fmtPct(val: number | null): string {
  if (val === null) return '-'
  return (val * 100).toFixed(2) + '%'
}

const var95Level = computed(() => {
  const v = props.risk.var95
  if (v === null) return 'info'
  if (v > -0.01) return 'success'
  if (v > -0.03) return 'warning'
  return 'danger'
})

const var99Level = computed(() => {
  const v = props.risk.var99
  if (v === null) return 'info'
  if (v > -0.015) return 'success'
  if (v > -0.05) return 'warning'
  return 'danger'
})

const tailRiskType = computed(() => {
  const w = props.risk.tailRiskWarning
  if (!w) return 'info'
  if (w.includes('显著')) return 'danger'
  if (w.includes('较低')) return 'success'
  return 'warning'
})
</script>

<template>
  <div class="risk-center">
    <div class="panel-title">风险评估</div>

    <div class="risk-section">
      <div class="section-label">VaR / CVaR</div>
      <div class="risk-grid">
        <div class="risk-item">
          <span class="risk-key">VaR 95%</span>
          <el-tag :type="var95Level" size="small" effect="plain">
            {{ fmtPct(risk.var95) }}
          </el-tag>
        </div>
        <div class="risk-item">
          <span class="risk-key">VaR 99%</span>
          <el-tag :type="var99Level" size="small" effect="plain">
            {{ fmtPct(risk.var99) }}
          </el-tag>
        </div>
        <div class="risk-item">
          <span class="risk-key">CVaR 95%</span>
          <span class="risk-val font-mono">{{ fmtPct(risk.cvar95) }}</span>
        </div>
        <div class="risk-item">
          <span class="risk-key">CVaR 99%</span>
          <span class="risk-val font-mono">{{ fmtPct(risk.cvar99) }}</span>
        </div>
      </div>
    </div>

    <div v-if="risk.stressTest" class="risk-section">
      <div class="section-label">蒙特卡洛压力测试</div>
      <div class="risk-grid">
        <div class="risk-item">
          <span class="risk-key">信号翻转率</span>
          <span class="risk-val font-mono">
            {{ risk.stressTest.signalFlipRate != null ? (risk.stressTest.signalFlipRate * 100).toFixed(1) + '%' : '-' }}
          </span>
        </div>
        <div class="risk-item">
          <span class="risk-key">稳健性</span>
          <el-tag
            v-if="risk.stressTest.isRobust != null"
            :type="risk.stressTest.isRobust ? 'success' : 'danger'"
            size="small"
            effect="dark"
          >
            {{ risk.stressTest.isRobust ? '稳健' : '脆弱' }}
          </el-tag>
          <span v-else class="risk-val">-</span>
        </div>
      </div>
    </div>

    <div v-if="risk.tailRiskWarning" class="risk-section">
      <div class="section-label">尾部风险</div>
      <el-tag :type="tailRiskType" size="small" effect="dark">
        {{ risk.tailRiskWarning }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped>
.risk-center {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: var(--transition-base);
}

.risk-center:hover {
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

.risk-section {
  margin-bottom: 14px;
}

.risk-section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 600;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.risk-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.risk-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.risk-key {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.risk-val {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 600;
}
</style>
