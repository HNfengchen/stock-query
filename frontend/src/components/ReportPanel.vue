<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisResult } from '@/types'

const props = defineProps<{ result: AnalysisResult }>()

const signalColor = computed(() => {
  const signal = props.result.trading_signal?.signal || ''
  if (signal.includes('buy')) return 'var(--color-up)'
  if (signal.includes('sell')) return 'var(--color-down)'
  return 'var(--color-warn)'
})

const scorePercent = computed(() => {
  return Math.round((props.result.trading_signal?.score || 0) * 100)
})

const ps = computed<any>(() => props.result.position_strategy || ({} as any))

const isHeld = computed(() => 'avg_cost' in ps.value)

const profitBelowCost = computed(() => {
  return isHeld.value && ps.value.stop_profit_price != null && ps.value.avg_cost != null && ps.value.stop_profit_price < ps.value.avg_cost
})

function fmt(val: any) {
  if (val === null || val === undefined) return '-'
  const num = Number(val)
  if (isNaN(num)) return String(val)
  return num.toFixed(2)
}

function getTrendType(trend: string) {
  if (trend === 'up') return 'success'
  if (trend === 'down') return 'danger'
  return 'warning'
}
</script>

<template>
  <div class="report-panel">
    <div class="info-row">
      <!-- 交易信号 -->
      <div class="info-card signal-card" :style="{ borderColor: signalColor }">
        <div class="card-label">交易信号</div>
        <div class="signal-main">
          <span class="signal-text" :style="{ color: signalColor }">
            {{ result.trading_signal?.signal_text || '持有' }}
          </span>
          <el-progress
            type="dashboard"
            :percentage="scorePercent"
            :color="signalColor"
            :stroke-width="6"
            :width="56"
          />
        </div>
        <div class="signal-score-text">
          综合评分: {{ result.trading_signal?.score?.toFixed(3) || '0.500' }}
        </div>
      </div>

      <!-- 价格预测 -->
      <div class="info-card prediction-card">
        <div class="card-label">价格预测</div>
        <div class="pred-row">
          <div class="pred-item">
            <span class="pred-label">当前价</span>
            <span class="pred-val font-mono">{{ fmt(result.price_prediction?.current) }}</span>
          </div>
          <div class="pred-item">
            <span class="pred-label">支撑</span>
            <span class="pred-val support font-mono">{{ fmt(result.price_prediction?.support) }}</span>
          </div>
          <div class="pred-item">
            <span class="pred-label">压力</span>
            <span class="pred-val resistance font-mono">{{ fmt(result.price_prediction?.resistance) }}</span>
          </div>
        </div>
        <div class="pred-days">
          <div class="pred-day">
            <span class="day-label">Day1</span>
            <span class="day-range font-mono">
              {{ fmt(result.price_prediction?.day1?.target_low) }} ~ {{ fmt(result.price_prediction?.day1?.target_high) }}
            </span>
            <el-tag
              size="small"
              :type="getTrendType(result.price_prediction?.day1?.trend)"
              effect="dark"
            >
              {{ result.price_prediction?.day1?.signal }}
            </el-tag>
          </div>
          <div class="pred-day">
            <span class="day-label">Day2</span>
            <span class="day-range font-mono">
              {{ fmt(result.price_prediction?.day2?.target_low) }} ~ {{ fmt(result.price_prediction?.day2?.target_high) }}
            </span>
            <el-tag
              size="small"
              :type="getTrendType(result.price_prediction?.day2?.trend)"
              effect="dark"
            >
              {{ result.price_prediction?.day2?.signal }}
            </el-tag>
          </div>
        </div>
      </div>

      <!-- 持仓策略 -->
      <div class="info-card strategy-card">
        <div class="card-label">持仓策略</div>
        <template v-if="isHeld">
          <div class="strat-grid">
            <div class="strat-item">
              <span class="strat-label">成本</span>
              <span class="strat-val font-mono">{{ fmt(ps.avg_cost) }}</span>
            </div>
            <div class="strat-item">
              <span class="strat-label">盈亏</span>
              <span
                class="strat-val font-mono"
                :class="(ps.price_change_pct || 0) >= 0 ? 'profit' : 'loss'"
              >
                {{ fmt(ps.price_change_pct) }}%
              </span>
            </div>
            <div class="strat-item">
              <span class="strat-label">{{ profitBelowCost ? '目标' : '止盈' }}</span>
              <span
                class="strat-val font-mono"
                :class="profitBelowCost ? 'warn' : 'profit'"
              >
                {{ fmt(ps.stop_profit_price) }}
              </span>
            </div>
            <div class="strat-item">
              <span class="strat-label">止损</span>
              <span class="strat-val loss font-mono">{{ fmt(ps.stop_loss_price) }}</span>
            </div>
          </div>
          <div class="strat-action">
            <el-tag
              :type="ps.position_adjust?.includes('减仓') ? 'danger' : ps.position_adjust?.includes('补仓') ? 'success' : 'info'"
              effect="dark"
              size="small"
            >
              {{ ps.position_adjust }}
            </el-tag>
          </div>
        </template>
        <template v-else>
          <div class="strat-grid">
            <div class="strat-item">
              <span class="strat-label">时机</span>
              <el-tag
                :type="ps.buy_timing?.includes('建议') ? 'success' : 'warning'"
                effect="dark"
                size="small"
              >
                {{ ps.buy_timing }}
              </el-tag>
            </div>
            <div class="strat-item">
              <span class="strat-label">仓位</span>
              <span class="strat-val font-mono">{{ ps.position_size_pct }}%</span>
            </div>
            <div class="strat-item">
              <span class="strat-label">止损</span>
              <span class="strat-val loss font-mono">{{ fmt(ps.stop_loss_price) }}</span>
            </div>
            <div class="strat-item">
              <span class="strat-label">风险</span>
              <el-tag
                :type="ps.risk_level?.includes('低') ? 'success' : ps.risk_level?.includes('高') ? 'danger' : 'warning'"
                effect="dark"
                size="small"
              >
                {{ ps.risk_level }}
              </el-tag>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 技术指标 -->
    <div class="indicators-row">
      <div v-if="result.indicators?.MACD" class="ind-chip">
        <span class="ind-name">MACD</span>
        <span
          class="ind-signal"
          :class="result.indicators.MACD.signal?.includes('金叉') ? 'bull' : result.indicators.MACD.signal?.includes('死叉') ? 'bear' : 'neutral'"
        >
          {{ result.indicators.MACD.signal }}
        </span>
        <span v-if="result.indicators.MACD.latest" class="ind-detail font-mono">
          DIF {{ fmt(result.indicators.MACD.latest.DIF) }} / DEA {{ fmt(result.indicators.MACD.latest.DEA) }}
        </span>
      </div>
      <div v-if="result.indicators?.RSI?.['RSI(12)']" class="ind-chip">
        <span class="ind-name">RSI(12)</span>
        <span
          class="ind-signal"
          :class="result.indicators.RSI['RSI(12)']?.signal?.includes('超买') ? 'bear' : result.indicators.RSI['RSI(12)']?.signal?.includes('超卖') ? 'bull' : 'neutral'"
        >
          {{ result.indicators.RSI['RSI(12)']?.signal }}
        </span>
        <span class="ind-detail font-mono">{{ fmt(result.indicators.RSI['RSI(12)']?.latest) }}</span>
      </div>
      <div v-if="result.indicators?.KDJ" class="ind-chip">
        <span class="ind-name">KDJ</span>
        <span
          class="ind-signal"
          :class="result.indicators.KDJ.signal?.includes('金叉') ? 'bull' : result.indicators.KDJ.signal?.includes('死叉') ? 'bear' : 'neutral'"
        >
          {{ result.indicators.KDJ.signal }}
        </span>
        <span v-if="result.indicators.KDJ.latest" class="ind-detail font-mono">
          K {{ fmt(result.indicators.KDJ.latest.K) }} D {{ fmt(result.indicators.KDJ.latest.D) }} J {{ fmt(result.indicators.KDJ.latest.J) }}
        </span>
      </div>
      <div v-if="result.indicators?.BOLL?.latest" class="ind-chip">
        <span class="ind-name">BOLL</span>
        <span
          class="ind-signal"
          :class="result.indicators.BOLL.latest.bandwidth < 10 ? 'bull' : result.indicators.BOLL.latest.bandwidth > 25 ? 'bear' : 'neutral'"
        >
          {{ result.indicators.BOLL.latest.bandwidth < 10 ? '收窄' : result.indicators.BOLL.latest.bandwidth > 25 ? '扩张' : '平稳' }}
        </span>
        <span class="ind-detail font-mono">带宽 {{ fmt(result.indicators.BOLL.latest.bandwidth) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-row {
  display: grid;
  grid-template-columns: 1fr 1.5fr 1fr;
  gap: 16px;
}

.info-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  transition: var(--transition-base);
}

.info-card:hover {
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

.signal-card {
  border-left: 3px solid v-bind(signalColor);
}

.signal-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.signal-text {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.signal-score-text {
  font-size: 12px;
  color: var(--text-muted);
}

.pred-row {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.pred-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pred-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.pred-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.pred-val.support { color: var(--color-up); }
.pred-val.resistance { color: var(--color-down); }

.pred-days {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pred-day {
  display: flex;
  align-items: center;
  gap: 12px;
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
  flex: 1;
  font-weight: 600;
}

.strat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.strat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.strat-label {
  font-size: 12px;
  color: var(--text-muted);
  width: 36px;
  flex-shrink: 0;
  font-weight: 500;
}

.strat-val {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.strat-val.profit { color: var(--color-up); }
.strat-val.loss { color: var(--color-down); }
.strat-val.warn { color: var(--color-warn); }

.strat-action {
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.indicators-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.ind-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition: var(--transition-fast);
}

.ind-chip:hover {
  border-color: var(--border-active);
}

.ind-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.03em;
}

.ind-signal {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.ind-signal.bull { background: var(--color-up-dim); color: var(--color-up); }
.ind-signal.bear { background: var(--color-down-dim); color: var(--color-down); }
.ind-signal.neutral { background: rgba(245, 158, 11, 0.15); color: var(--color-warn); }

.ind-detail {
  font-size: 11px;
  color: var(--text-muted);
}

@media (max-width: 1024px) {
  .info-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .pred-row {
    flex-wrap: wrap;
    gap: 12px;
  }
  .indicators-row {
    flex-direction: column;
  }
  .ind-chip {
    justify-content: space-between;
  }
}
</style>
