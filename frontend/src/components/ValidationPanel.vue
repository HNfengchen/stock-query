<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisValidation, StressTestResult } from '@/types'

const props = defineProps<{ validation: AnalysisValidation }>()

const consensusMap: Record<string, { label: string; type: string; icon: string; desc: string }> = {
  bullish: { label: '看多', type: 'success', icon: '📈', desc: '多数指标看涨，方向一致' },
  bearish: { label: '看空', type: 'danger', icon: '📉', desc: '多数指标看跌，方向一致' },
  mixed: { label: '分歧', type: 'warning', icon: '↔️', desc: '多空指标分歧较大，方向不明' },
}

const riskMap: Record<string, { label: string; type: string; icon: string; desc: string }> = {
  low: { label: '低风险', type: 'success', icon: '🛡️', desc: '指标一致性好，信号可靠' },
  medium: { label: '中风险', type: 'warning', icon: '⚠️', desc: '存在部分分歧，需谨慎' },
  high: { label: '高风险', type: 'danger', icon: '🔴', desc: '指标冲突明显，信号不确定' },
}

const gateMap: Record<string, { label: string; type: string; icon: string; desc: string }> = {
  allow_buy: { label: '允许买入', type: 'success', icon: '✅', desc: '看多共识+高置信度，可考虑建仓' },
  cautious_buy: { label: '谨慎买入', type: 'warning', icon: '⚠️', desc: '看多但置信度不足，轻仓试探' },
  avoid_buy: { label: '不建议买入', type: 'danger', icon: '🚫', desc: '看空共识明显，不宜介入' },
  watch: { label: '观望', type: 'info', icon: '👀', desc: '信号不明确，继续等待' },
  reduce_position: { label: '建议减仓', type: 'danger', icon: '⬇️', desc: '看空共识+高风险，建议降低仓位' },
  cautious_hold: { label: '谨慎持有', type: 'warning', icon: '⚠️', desc: '偏空但风险可控，密切关注' },
  hold_position: { label: '继续持有', type: 'success', icon: '⏸️', desc: '未达减仓条件，维持当前仓位' },
}

const consensusInfo = computed(() => consensusMap[props.validation.direction_consensus] || { label: props.validation.direction_consensus, type: 'info', icon: '❓', desc: '' })
const riskInfo = computed(() => riskMap[props.validation.risk_level] || { label: props.validation.risk_level, type: 'info', icon: '❓', desc: '' })
const gateInfo = computed(() => gateMap[props.validation.action_gate] || { label: props.validation.action_gate, type: 'info', icon: '❓', desc: '' })

const confidencePct = computed(() => Math.round((props.validation.confidence || 0) * 100))

const bullPct = computed(() => {
  const total = (props.validation.active_weight_total || 1)
  const bull = props.validation.weighted_bullish || 0
  return Math.round((bull / total) * 100)
})

const bearPct = computed(() => {
  const total = (props.validation.active_weight_total || 1)
  const bear = props.validation.weighted_bearish || 0
  return Math.round((bear / total) * 100)
})

const confidenceColor = computed(() => {
  const v = confidencePct.value
  if (v >= 70) return 'var(--color-up)'
  if (v >= 45) return 'var(--color-warn)'
  return 'var(--color-down)'
})

const confidenceDesc = computed(() => {
  const v = confidencePct.value
  if (v >= 80) return '信号非常可靠'
  if (v >= 70) return '信号较为可靠'
  if (v >= 50) return '信号可靠性一般'
  if (v >= 30) return '信号可靠性较低'
  return '信号不可靠'
})

const stressTest = computed(() => props.validation.stress_test)

const flipRatePct = computed(() => {
  if (!stressTest.value || stressTest.value.signal_flip_rate == null) return null
  return Math.round(stressTest.value.signal_flip_rate * 100)
})

const flipRateColor = computed(() => {
  if (!stressTest.value || stressTest.value.signal_flip_rate == null) return 'var(--text-muted)'
  const rate = stressTest.value.signal_flip_rate
  if (rate < 0.15) return 'var(--color-up)'
  if (rate < 0.30) return 'var(--color-warn)'
  return 'var(--color-down)'
})

const flipRateType = computed(() => {
  if (!stressTest.value || stressTest.value.signal_flip_rate == null) return 'info'
  const rate = stressTest.value.signal_flip_rate
  if (rate < 0.15) return 'success'
  if (rate < 0.30) return 'warning'
  return 'danger'
})

function hasItems(list: string[] | undefined | null): boolean {
  return Array.isArray(list) && list.length > 0
}

function formatMetric(value: number | null | undefined, fallback: string = 'N/A'): string {
  if (value === undefined || value === null || !isFinite(value)) return fallback
  return value.toFixed(2)
}
</script>

<template>
  <div class="validation-panel">
    <div class="card-label">交叉验证</div>

    <div class="v-row">
      <div class="v-chip">
        <span class="v-chip-label">方向共识</span>
        <el-tag :type="consensusInfo.type" effect="dark" size="small">
          {{ consensusInfo.icon }} {{ consensusInfo.label }}
        </el-tag>
        <span class="v-chip-desc">{{ consensusInfo.desc }}</span>
      </div>
      <div class="v-chip">
        <span class="v-chip-label">置信度</span>
        <div class="conf-bar-wrap">
          <el-progress
            :percentage="confidencePct"
            :color="confidenceColor"
            :stroke-width="8"
            :width="80"
            type="dashboard"
          />
          <div class="conf-detail">
            <span class="conf-text">{{ confidencePct }}%</span>
            <span class="conf-desc">{{ confidenceDesc }}</span>
          </div>
        </div>
      </div>
      <div class="v-chip">
        <span class="v-chip-label">风险等级</span>
        <el-tag :type="riskInfo.type" effect="dark" size="small">
          {{ riskInfo.icon }} {{ riskInfo.label }}
        </el-tag>
        <span class="v-chip-desc">{{ riskInfo.desc }}</span>
      </div>
      <div class="v-chip">
        <span class="v-chip-label">操作建议</span>
        <el-tag :type="gateInfo.type" effect="dark" size="small">
          {{ gateInfo.icon }} {{ gateInfo.label }}
        </el-tag>
        <span class="v-chip-desc">{{ gateInfo.desc }}</span>
      </div>
    </div>

    <div v-if="validation.missing_dimensions && validation.missing_dimensions.length" class="v-missing">
      <span class="missing-label">⚠️ 数据缺失</span>
      <div class="missing-list">
        <el-tag
          v-for="d in validation.missing_dimensions"
          :key="d"
          type="info"
          size="small"
          effect="plain"
        >
          {{ d }}数据不可用
        </el-tag>
      </div>
    </div>

    <div v-if="validation.signal_persistence && Object.keys(validation.signal_persistence).length" class="v-persistence">
      <span class="persistence-label">📊 信号持续性</span>
      <div class="persistence-list">
        <el-tag
          v-for="(info, key) in validation.signal_persistence"
          :key="key"
          :type="info.direction === 'bullish' || info.direction === 'oversold' ? 'success' : 'danger'"
          size="small"
          effect="plain"
        >
          {{ key === 'macd_persistence' ? 'MACD' : 'RSI' }} {{ info.direction === 'bullish' ? '多头' : info.direction === 'bearish' ? '空头' : info.direction === 'overbought' ? '超买' : '超卖' }} {{ info.days }}日
        </el-tag>
      </div>
    </div>

    <div v-if="stressTest" class="v-stress-test">
      <span class="stress-label">🎲 蒙特卡洛压力测试</span>
      <div class="stress-content">
        <div class="stress-row">
          <div class="stress-item">
            <span class="stress-item-label">信号翻转率</span>
            <el-tag :type="flipRateType" effect="dark" size="small">
              {{ flipRatePct != null ? flipRatePct + '%' : '-' }}
            </el-tag>
          </div>
          <div class="stress-item">
            <span class="stress-item-label">鲁棒性</span>
            <el-tag :type="stressTest.is_robust ? 'success' : 'danger'" effect="dark" size="small">
              {{ stressTest.is_robust ? '✅ 鲁棒' : '⚠️ 不鲁棒' }}
            </el-tag>
          </div>
          <div class="stress-item">
            <span class="stress-item-label">原始信号</span>
            <el-tag type="info" size="small" effect="plain">{{ stressTest.original_signal }}</el-tag>
          </div>
          <div class="stress-item">
            <span class="stress-item-label">模拟次数</span>
            <span class="stress-metric-val">{{ stressTest.simulation_count }}</span>
          </div>
        </div>
        <div v-if="stressTest.risk_metrics" class="stress-metrics">
          <div class="stress-metric">
            <span class="stress-metric-label">最大回撤</span>
            <span class="stress-metric-val">{{ stressTest.risk_metrics.max_drawdown != null ? formatMetric(stressTest.risk_metrics.max_drawdown * 100) + '%' : '-' }}</span>
          </div>
          <div class="stress-metric">
            <span class="stress-metric-label">Sharpe</span>
            <span class="stress-metric-val">{{ formatMetric(stressTest.risk_metrics.sharpe) }}</span>
          </div>
          <div class="stress-metric">
            <span class="stress-metric-label">Sortino</span>
            <span class="stress-metric-val">{{ formatMetric(stressTest.risk_metrics.sortino) }}</span>
          </div>
          <div class="stress-metric">
            <span class="stress-metric-label">Calmar</span>
            <span class="stress-metric-val">{{ formatMetric(stressTest.risk_metrics.calmar) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="validation.weighted_bullish !== undefined || validation.weighted_bearish !== undefined" class="v-weighted">
      <div class="weight-bar">
        <div class="weight-bar-fill bull" :style="{ width: bullPct + '%' }"></div>
        <div class="weight-bar-fill bear" :style="{ width: bearPct + '%' }"></div>
      </div>
      <div class="weight-labels">
        <span class="weight-bull">看多 {{ bullPct }}%</span>
        <span class="weight-bear">看空 {{ bearPct }}%</span>
      </div>
    </div>

    <div v-if="hasItems(validation.supporting_factors) || hasItems(validation.opposing_factors) || hasItems(validation.conflicts)" class="v-factors">
      <div v-if="hasItems(validation.supporting_factors)" class="v-factor-group">
        <span class="factor-label support-label">👍 利好</span>
        <div class="factor-list">
          <el-tag
            v-for="f in validation.supporting_factors"
            :key="f"
            type="success"
            size="small"
            effect="plain"
          >
            {{ f }}
          </el-tag>
        </div>
      </div>
      <div v-if="hasItems(validation.opposing_factors)" class="v-factor-group">
        <span class="factor-label oppose-label">👎 利空</span>
        <div class="factor-list">
          <el-tag
            v-for="f in validation.opposing_factors"
            :key="f"
            type="danger"
            size="small"
            effect="plain"
          >
            {{ f }}
          </el-tag>
        </div>
      </div>
      <div v-if="hasItems(validation.conflicts)" class="v-factor-group">
        <span class="factor-label conflict-label">⚡ 冲突</span>
        <div class="factor-list">
          <el-tag
            v-for="f in validation.conflicts"
            :key="f"
            type="warning"
            size="small"
            effect="plain"
          >
            {{ f }}
          </el-tag>
        </div>
      </div>
    </div>

    <div v-if="validation.validation_note" class="v-note">
      {{ validation.validation_note }}
    </div>
  </div>
</template>

<style scoped>
.validation-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  transition: var(--transition-base);
}

.validation-panel:hover {
  border-color: var(--border-active);
}

.card-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 16px;
}

.v-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.v-chip {
  display: flex;
  align-items: center;
  gap: 8px;
}

.v-chip-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}

.v-chip-desc {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  max-width: 120px;
  line-height: 1.3;
}

.conf-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.conf-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conf-text {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.conf-desc {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.v-factors {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.v-missing {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
}

.missing-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-warn);
  white-space: nowrap;
  padding-top: 3px;
  min-width: 72px;
}

.missing-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.v-persistence {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 10px;
}

.persistence-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  padding-top: 3px;
  min-width: 72px;
}

.persistence-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.v-stress-test {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm, 6px);
}

.stress-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  padding-top: 3px;
  min-width: 120px;
}

.stress-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stress-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stress-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stress-item-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.stress-metrics {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stress-metric {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stress-metric-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  white-space: nowrap;
}

.stress-metric-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.v-weighted {
  margin-top: 12px;
}

.weight-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  background: var(--border-subtle);
  overflow: hidden;
}

.weight-bar-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.weight-bar-fill.bull {
  background: var(--color-up);
  border-radius: 3px 0 0 3px;
}

.weight-bar-fill.bear {
  background: var(--color-down);
  border-radius: 0 3px 3px 0;
}

.weight-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 10px;
}

.weight-bull {
  color: var(--color-up);
}

.weight-bear {
  color: var(--color-down);
}

.v-factor-group {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.factor-label {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  padding-top: 3px;
  min-width: 52px;
}

.support-label { color: var(--color-up); }
.oppose-label { color: var(--color-down); }
.conflict-label { color: var(--color-warn); }

.factor-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.v-note {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

@media (max-width: 768px) {
  .v-row {
    flex-direction: column;
    gap: 12px;
  }
  .v-chip-desc {
    display: none;
  }
  .v-factor-group {
    flex-direction: column;
    gap: 6px;
  }
}
</style>
