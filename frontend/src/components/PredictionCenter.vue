<script setup lang="ts">
import { computed } from 'vue'
import type { PredictionResult } from '@/types'
import { fmtNum } from '@/utils/format'

const props = defineProps<{ prediction: PredictionResult }>()

const hasMl = computed(() => props.prediction.mlPrediction != null)
const alphaDisplay = computed(() => {
  const a = props.prediction.alpha
  if (a === null) return '-'
  return (a * 100).toFixed(0) + '% / ' + ((1 - a) * 100).toFixed(0) + '%'
})
const alphaLabel = computed(() => {
  const a = props.prediction.alpha
  if (a === null) return '-'
  return `规则 ${((a) * 100).toFixed(0)}% : ML ${((1 - a) * 100).toFixed(0)}%`
})
const confidencePct = computed(() => {
  const c = props.prediction.confidence
  if (c === null) return null
  return Math.round(c * 100)
})
const confidenceColor = computed(() => {
  const v = confidencePct.value
  if (v === null) return 'var(--text-muted)'
  if (v >= 70) return 'var(--color-up)'
  if (v >= 45) return 'var(--color-warn)'
  return 'var(--color-down)'
})
const mlDirection = computed(() => {
  const d = props.prediction.mlPrediction?.direction
  if (d === null || d === undefined) return '-'
  if (d >= 1) return '看涨'
  if (d <= 0) return '看跌'
  return '中性'
})
const mlDirectionType = computed(() => {
  const d = props.prediction.mlPrediction?.direction
  if (d === null || d === undefined) return 'info'
  if (d >= 1) return 'success'
  if (d <= 0) return 'danger'
  return 'warning'
})
</script>

<template>
  <div class="prediction-center">
    <div class="panel-title">预测中心</div>

    <div class="pred-section">
      <div class="section-label">混合预测区间</div>
      <div class="pred-days">
        <div class="pred-day">
          <span class="day-label">Day1</span>
          <span class="day-range font-mono">
            {{ fmtNum(prediction.hybridPrediction.day1Low) }} ~ {{ fmtNum(prediction.hybridPrediction.day1High) }}
          </span>
        </div>
        <div class="pred-day">
          <span class="day-label">Day2</span>
          <span class="day-range font-mono">
            {{ fmtNum(prediction.hybridPrediction.day2Low) }} ~ {{ fmtNum(prediction.hybridPrediction.day2High) }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="hasMl" class="pred-section">
      <div class="section-label">规则 vs ML 对比</div>
      <div class="compare-grid">
        <div class="compare-item">
          <span class="compare-key">混合权重</span>
          <span class="compare-val font-mono">{{ alphaLabel }}</span>
        </div>
        <div class="compare-item">
          <span class="compare-key">ML方向</span>
          <el-tag :type="mlDirectionType" size="small" effect="dark">
            {{ mlDirection }}
          </el-tag>
        </div>
        <div v-if="prediction.rulePrediction" class="compare-item">
          <span class="compare-key">规则Day1</span>
          <span class="compare-val font-mono">
            {{ fmtNum(prediction.rulePrediction.day1Low) }} ~ {{ fmtNum(prediction.rulePrediction.day1High) }}
          </span>
        </div>
        <div v-if="prediction.mlPrediction?.next_day_return != null" class="compare-item">
          <span class="compare-key">ML收益率</span>
          <span
            class="compare-val font-mono"
            :class="prediction.mlPrediction.next_day_return >= 0 ? 'up' : 'down'"
          >
            {{ (prediction.mlPrediction.next_day_return * 100).toFixed(2) }}%
          </span>
        </div>
      </div>
    </div>

    <div class="pred-section">
      <div class="section-label">置信度</div>
      <div class="confidence-row">
        <el-progress
          v-if="confidencePct !== null"
          :percentage="confidencePct"
          :color="confidenceColor"
          :stroke-width="8"
          :show-text="false"
        />
        <span class="confidence-val font-mono" :style="{ color: confidenceColor }">
          {{ confidencePct !== null ? confidencePct + '%' : '-' }}
        </span>
      </div>
      <div v-if="prediction.alpha != null" class="alpha-row">
        <span class="alpha-label">hybrid_alpha</span>
        <span class="alpha-val font-mono">{{ prediction.alpha.toFixed(2) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prediction-center {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: var(--transition-base);
}

.prediction-center:hover {
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

.pred-section {
  margin-bottom: 14px;
}

.pred-section:last-child {
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

.pred-days {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pred-day {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}

.day-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-up);
  width: 36px;
  letter-spacing: 0.05em;
}

.day-range {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.compare-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.compare-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.compare-key {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.compare-val {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 600;
}

.compare-val.up {
  color: var(--color-up);
}

.compare-val.down {
  color: var(--color-down);
}

.confidence-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.confidence-row .el-progress {
  flex: 1;
}

.confidence-val {
  font-size: 14px;
  font-weight: 700;
  min-width: 40px;
  text-align: right;
}

.alpha-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.alpha-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.alpha-val {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}
</style>
