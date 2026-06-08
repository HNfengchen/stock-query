<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import type { AnalysisValidation, StressTestResult } from '@/types'
import {
  TrendCharts,
  Bottom,
  Sort,
  Lock,
  Warning,
  CircleClose,
  CircleCheck,
  CloseBold,
  View,
  ArrowDown,
  VideoPause,
  QuestionFilled,
  Opportunity,
  CaretBottom,
  Lightning,
  DataLine,
  Coin,
} from '@element-plus/icons-vue'

const props = defineProps<{ validation: AnalysisValidation }>()

const consensusMap: Record<string, { label: string; type: string; icon: Component; desc: string }> = {
  bullish: { label: '看多', type: 'success', icon: TrendCharts, desc: '多数指标看涨，方向一致' },
  bearish: { label: '看空', type: 'danger', icon: Bottom, desc: '多数指标看跌，方向一致' },
  mixed: { label: '分歧', type: 'warning', icon: Sort, desc: '多空指标分歧较大，方向不明' },
}

const riskMap: Record<string, { label: string; type: string; icon: Component; desc: string }> = {
  low: { label: '低风险', type: 'success', icon: Lock, desc: '指标一致性好，信号可靠' },
  medium: { label: '中风险', type: 'warning', icon: Warning, desc: '存在部分分歧，需谨慎' },
  high: { label: '高风险', type: 'danger', icon: CircleClose, desc: '指标冲突明显，信号不确定' },
}

const gateMap: Record<string, { label: string; type: string; icon: Component; desc: string }> = {
  allow_buy: { label: '允许买入', type: 'success', icon: CircleCheck, desc: '看多共识+高置信度，可考虑建仓' },
  cautious_buy: { label: '谨慎买入', type: 'warning', icon: Warning, desc: '看多但置信度不足，轻仓试探' },
  avoid_buy: { label: '不建议买入', type: 'danger', icon: CloseBold, desc: '看空共识明显，不宜介入' },
  watch: { label: '观望', type: 'info', icon: View, desc: '信号不明确，继续等待' },
  reduce_position: { label: '建议减仓', type: 'danger', icon: ArrowDown, desc: '看空共识+高风险，建议降低仓位' },
  cautious_hold: { label: '谨慎持有', type: 'warning', icon: Warning, desc: '偏空但风险可控，密切关注' },
  hold_position: { label: '继续持有', type: 'success', icon: VideoPause, desc: '未达减仓条件，维持当前仓位' },
}

const consensusInfo = computed(() => consensusMap[props.validation.direction_consensus] || { label: props.validation.direction_consensus, type: 'info', icon: QuestionFilled, desc: '' })
const riskInfo = computed(() => riskMap[props.validation.risk_level] || { label: props.validation.risk_level, type: 'info', icon: QuestionFilled, desc: '' })
const gateInfo = computed(() => gateMap[props.validation.action_gate] || { label: props.validation.action_gate, type: 'info', icon: QuestionFilled, desc: '' })

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
  if (v >= 70) return 'var(--color-up, #26a69a)'
  if (v >= 45) return 'var(--color-warn, #ffa726)'
  return 'var(--color-down, #ef5350)'
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
  if (!stressTest.value || stressTest.value.signal_flip_rate == null) return 'var(--text-muted, rgba(255, 255, 255, 0.38))'
  const rate = stressTest.value.signal_flip_rate
  if (rate < 0.15) return 'var(--color-up, #26a69a)'
  if (rate < 0.30) return 'var(--color-warn, #ffa726)'
  return 'var(--color-down, #ef5350)'
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
          <el-icon><component :is="consensusInfo.icon" /></el-icon> {{ consensusInfo.label }}
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
          <el-icon><component :is="riskInfo.icon" /></el-icon> {{ riskInfo.label }}
        </el-tag>
        <span class="v-chip-desc">{{ riskInfo.desc }}</span>
      </div>
      <div class="v-chip">
        <span class="v-chip-label">操作建议</span>
        <el-tag :type="gateInfo.type" effect="dark" size="small">
          <el-icon><component :is="gateInfo.icon" /></el-icon> {{ gateInfo.label }}
        </el-tag>
        <span class="v-chip-desc">{{ gateInfo.desc }}</span>
      </div>
    </div>

    <div v-if="validation.missing_dimensions && validation.missing_dimensions.length" class="v-missing">
      <span class="missing-label"><el-icon><Warning /></el-icon> 数据缺失</span>
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
      <span class="persistence-label"><el-icon><DataLine /></el-icon> 信号持续性</span>
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
      <div class="stress-header">
        <el-icon><Coin /></el-icon>
        <span class="stress-title">蒙特卡洛压力测试</span>
      </div>
      <div class="stress-grid">
        <div class="stress-cell">
          <span class="stress-cell-label">信号翻转率</span>
          <span class="stress-cell-val" :style="{ color: flipRateColor }">
            {{ flipRatePct != null ? flipRatePct + '%' : '-' }}
          </span>
        </div>
        <div class="stress-cell">
          <span class="stress-cell-label">鲁棒性</span>
          <span class="stress-cell-val" :class="stressTest.is_robust ? 'up' : 'down'">
            {{ stressTest.is_robust ? '鲁棒' : '不鲁棒' }}
          </span>
        </div>
        <div class="stress-cell">
          <span class="stress-cell-label">原始信号</span>
          <span class="stress-cell-val">{{ stressTest.original_signal }}</span>
        </div>
        <div class="stress-cell">
          <span class="stress-cell-label">模拟次数</span>
          <span class="stress-cell-val">{{ stressTest.simulation_count }}</span>
        </div>
        <div v-if="stressTest.risk_metrics" class="stress-cell">
          <span class="stress-cell-label">最大回撤</span>
          <span class="stress-cell-val" :class="(stressTest.risk_metrics.max_drawdown || 0) > 0.2 ? 'down' : 'up'">
            {{ stressTest.risk_metrics.max_drawdown != null ? formatMetric(stressTest.risk_metrics.max_drawdown * 100) + '%' : '-' }}
          </span>
        </div>
        <div v-if="stressTest.risk_metrics" class="stress-cell">
          <span class="stress-cell-label">Sharpe</span>
          <span class="stress-cell-val">{{ formatMetric(stressTest.risk_metrics.sharpe) }}</span>
        </div>
        <div v-if="stressTest.risk_metrics" class="stress-cell">
          <span class="stress-cell-label">Sortino</span>
          <span class="stress-cell-val">{{ formatMetric(stressTest.risk_metrics.sortino) }}</span>
        </div>
        <div v-if="stressTest.risk_metrics" class="stress-cell">
          <span class="stress-cell-label">Calmar</span>
          <span class="stress-cell-val">{{ formatMetric(stressTest.risk_metrics.calmar) }}</span>
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
        <span class="factor-label support-label"><el-icon><Opportunity /></el-icon> 利好</span>
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
        <span class="factor-label oppose-label"><el-icon><CaretBottom /></el-icon> 利空</span>
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
        <span class="factor-label conflict-label"><el-icon><Lightning /></el-icon> 冲突</span>
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
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 20px;
  transition: var(--transition-base, 0.25s ease);
}

.validation-panel:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.card-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
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
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
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
  color: var(--color-warn, #ffa726);
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
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  margin-top: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  border-radius: var(--radius-sm, 6px);
}

.stress-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  letter-spacing: 0.04em;
}

.stress-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.stress-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--radius-sm, 6px);
  flex: 1 1 100px;
  min-width: 100px;
  max-width: 160px;
}

.stress-cell-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  white-space: nowrap;
}

.stress-cell-val {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
  word-break: keep-all;
}

.stress-cell-val.up {
  color: var(--color-up, #26a69a);
}

.stress-cell-val.down {
  color: var(--color-down, #ef5350);
}

.v-weighted {
  margin-top: 12px;
}

.weight-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.05));
  overflow: hidden;
}

.weight-bar-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.weight-bar-fill.bull {
  background: var(--color-up, #26a69a);
  border-radius: 3px 0 0 3px;
}

.weight-bar-fill.bear {
  background: var(--color-down, #ef5350);
  border-radius: 0 3px 3px 0;
}

.weight-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 10px;
}

.weight-bull {
  color: var(--color-up, #26a69a);
}

.weight-bear {
  color: var(--color-down, #ef5350);
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

.support-label { color: var(--color-up, #26a69a); }
.oppose-label { color: var(--color-down, #ef5350); }
.conflict-label { color: var(--color-warn, #ffa726); }

.factor-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.factor-list .el-tag {
  white-space: normal;
  word-break: break-all;
  height: auto;
  line-height: 1.4;
}

.v-note {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
