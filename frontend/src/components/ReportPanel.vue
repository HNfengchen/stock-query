<script setup lang="ts">
import { computed } from 'vue'
import type { AnalysisResult } from '@/types'

const props = defineProps<{ result: AnalysisResult }>()

const signalColor = computed(() => {
  const signal = props.result.trading_signal?.signal || ''
  if (signal.includes('buy')) return '#00d4aa'
  if (signal.includes('sell')) return '#ff4757'
  return '#f0a030'
})

const scorePercent = computed(() => {
  return Math.round((props.result.trading_signal?.score || 0) * 100)
})

const isHeld = computed(() => {
  return 'avg_cost' in (props.result.position_strategy || {})
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
    <!-- 第一行：交易信号 + 价格预测 + 持仓策略 -->
    <div class="info-row">
      <!-- 交易信号 -->
      <div class="info-card signal-card" :style="{ borderColor: signalColor }">
        <div class="card-label">交易信号</div>
        <div class="signal-main">
          <span class="signal-text" :style="{ color: signalColor }">{{ result.trading_signal?.signal_text || '持有' }}</span>
          <el-progress type="dashboard" :percentage="scorePercent" :color="signalColor" :stroke-width="6" :width="56" />
        </div>
        <div class="signal-score-text">综合评分: {{ result.trading_signal?.score?.toFixed(3) || '0.500' }}</div>
      </div>

      <!-- 价格预测 -->
      <div class="info-card prediction-card">
        <div class="card-label">价格预测</div>
        <div class="pred-row">
          <div class="pred-item">
            <span class="pred-label">当前价</span>
            <span class="pred-val">{{ fmt(result.price_prediction?.current) }}</span>
          </div>
          <div class="pred-item">
            <span class="pred-label">支撑</span>
            <span class="pred-val support">{{ fmt(result.price_prediction?.support) }}</span>
          </div>
          <div class="pred-item">
            <span class="pred-label">压力</span>
            <span class="pred-val resistance">{{ fmt(result.price_prediction?.resistance) }}</span>
          </div>
        </div>
        <div class="pred-days">
          <div class="pred-day">
            <span class="day-label">Day1</span>
            <span class="day-range">{{ fmt(result.price_prediction?.day1?.target_low) }} ~ {{ fmt(result.price_prediction?.day1?.target_high) }}</span>
            <el-tag size="small" :type="getTrendType(result.price_prediction?.day1?.trend)" effect="dark">{{ result.price_prediction?.day1?.signal }}</el-tag>
          </div>
          <div class="pred-day">
            <span class="day-label">Day2</span>
            <span class="day-range">{{ fmt(result.price_prediction?.day2?.target_low) }} ~ {{ fmt(result.price_prediction?.day2?.target_high) }}</span>
            <el-tag size="small" :type="getTrendType(result.price_prediction?.day2?.trend)" effect="dark">{{ result.price_prediction?.day2?.signal }}</el-tag>
          </div>
        </div>
      </div>

      <!-- 持仓策略 -->
      <div class="info-card strategy-card">
        <div class="card-label">持仓策略</div>
        <template v-if="isHeld">
          <div class="strat-grid">
            <div class="strat-item"><span class="strat-label">成本</span><span class="strat-val">{{ fmt((result.position_strategy as any).avg_cost) }}</span></div>
            <div class="strat-item"><span class="strat-label">盈亏</span><span class="strat-val" :class="((result.position_strategy as any).price_change_pct || 0) >= 0 ? 'profit' : 'loss'">{{ fmt((result.position_strategy as any).price_change_pct) }}%</span></div>
            <div class="strat-item"><span class="strat-label">止盈</span><span class="strat-val profit">{{ fmt((result.position_strategy as any).stop_profit_price) }}</span></div>
            <div class="strat-item"><span class="strat-label">止损</span><span class="strat-val loss">{{ fmt((result.position_strategy as any).stop_loss_price) }}</span></div>
          </div>
          <div class="strat-action">
            <el-tag :type="(result.position_strategy as any).position_adjust?.includes('减仓') ? 'danger' : (result.position_strategy as any).position_adjust?.includes('补仓') ? 'success' : 'info'" effect="dark" size="small">{{ (result.position_strategy as any).position_adjust }}</el-tag>
          </div>
        </template>
        <template v-else>
          <div class="strat-grid">
            <div class="strat-item"><span class="strat-label">时机</span><el-tag :type="(result.position_strategy as any).buy_timing?.includes('建议') ? 'success' : 'warning'" effect="dark" size="small">{{ (result.position_strategy as any).buy_timing }}</el-tag></div>
            <div class="strat-item"><span class="strat-label">仓位</span><span class="strat-val">{{ (result.position_strategy as any).position_size_pct }}%</span></div>
            <div class="strat-item"><span class="strat-label">止损</span><span class="strat-val loss">{{ fmt((result.position_strategy as any).stop_loss_price) }}</span></div>
            <div class="strat-item"><span class="strat-label">风险</span><el-tag :type="(result.position_strategy as any).risk_level?.includes('低') ? 'success' : (result.position_strategy as any).risk_level?.includes('高') ? 'danger' : 'warning'" effect="dark" size="small">{{ (result.position_strategy as any).risk_level }}</el-tag></div>
          </div>
        </template>
      </div>
    </div>

    <!-- 第二行：技术指标 -->
    <div class="indicators-row">
      <div v-if="result.indicators?.MACD" class="ind-chip">
        <span class="ind-name">MACD</span>
        <span class="ind-signal" :class="result.indicators.MACD.signal?.includes('金叉') ? 'bull' : result.indicators.MACD.signal?.includes('死叉') ? 'bear' : 'neutral'">{{ result.indicators.MACD.signal }}</span>
        <span v-if="result.indicators.MACD.latest" class="ind-detail">DIF {{ fmt(result.indicators.MACD.latest.DIF) }} / DEA {{ fmt(result.indicators.MACD.latest.DEA) }}</span>
      </div>
      <div v-if="result.indicators?.RSI?.['RSI(12)']" class="ind-chip">
        <span class="ind-name">RSI(12)</span>
        <span class="ind-signal" :class="result.indicators.RSI['RSI(12)']?.signal?.includes('超买') ? 'bear' : result.indicators.RSI['RSI(12)']?.signal?.includes('超卖') ? 'bull' : 'neutral'">{{ result.indicators.RSI['RSI(12)']?.signal }}</span>
        <span class="ind-detail">{{ fmt(result.indicators.RSI['RSI(12)']?.latest) }}</span>
      </div>
      <div v-if="result.indicators?.KDJ" class="ind-chip">
        <span class="ind-name">KDJ</span>
        <span class="ind-signal" :class="result.indicators.KDJ.signal?.includes('金叉') ? 'bull' : result.indicators.KDJ.signal?.includes('死叉') ? 'bear' : 'neutral'">{{ result.indicators.KDJ.signal }}</span>
        <span v-if="result.indicators.KDJ.latest" class="ind-detail">K {{ fmt(result.indicators.KDJ.latest.K) }} D {{ fmt(result.indicators.KDJ.latest.D) }} J {{ fmt(result.indicators.KDJ.latest.J) }}</span>
      </div>
      <div v-if="result.indicators?.BOLL?.latest" class="ind-chip">
        <span class="ind-name">BOLL</span>
        <span class="ind-signal" :class="result.indicators.BOLL.latest.bandwidth < 10 ? 'bull' : result.indicators.BOLL.latest.bandwidth > 25 ? 'bear' : 'neutral'">{{ result.indicators.BOLL.latest.bandwidth < 10 ? '收窄' : result.indicators.BOLL.latest.bandwidth > 25 ? '扩张' : '平稳' }}</span>
        <span class="ind-detail">带宽 {{ fmt(result.indicators.BOLL.latest.bandwidth) }}%</span>
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
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 16px;
}

.card-label {
  font-size: 12px;
  color: #8b92a8;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
}

.signal-card {
  border-color: v-bind(signalColor);
}

.signal-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.signal-text {
  font-size: 22px;
  font-weight: 700;
}

.signal-score-text {
  font-size: 12px;
  color: #8b92a8;
}

.pred-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.pred-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pred-label {
  font-size: 11px;
  color: #8b92a8;
}

.pred-val {
  font-size: 15px;
  font-weight: 600;
  color: #e0e6ed;
}

.pred-val.support { color: #00d4aa; }
.pred-val.resistance { color: #ff4757; }

.pred-days {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pred-day {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 6px;
}

.day-label {
  font-size: 12px;
  font-weight: 700;
  color: #00d4aa;
  width: 32px;
}

.day-range {
  font-size: 12px;
  color: #e0e6ed;
  flex: 1;
}

.strat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 8px;
}

.strat-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.strat-label {
  font-size: 12px;
  color: #8b92a8;
  width: 32px;
  flex-shrink: 0;
}

.strat-val {
  font-size: 14px;
  font-weight: 600;
  color: #e0e6ed;
}

.strat-val.profit { color: #00d4aa; }
.strat-val.loss { color: #ff4757; }

.strat-action {
  text-align: center;
}

.indicators-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.ind-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.ind-name {
  font-size: 13px;
  font-weight: 700;
  color: #e0e6ed;
}

.ind-signal {
  font-size: 12px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
}

.ind-signal.bull { background: rgba(0, 212, 170, 0.15); color: #00d4aa; }
.ind-signal.bear { background: rgba(255, 71, 87, 0.15); color: #ff4757; }
.ind-signal.neutral { background: rgba(240, 160, 48, 0.15); color: #f0a030; }

.ind-detail {
  font-size: 11px;
  color: #8b92a8;
}

@media (max-width: 1024px) {
  .info-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .pred-row {
    flex-wrap: wrap;
  }
  .indicators-row {
    flex-direction: column;
  }
}
</style>
