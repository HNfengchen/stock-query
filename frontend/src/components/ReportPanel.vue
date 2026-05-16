<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AnalysisResult } from '@/types'
import ValidationPanel from '@/components/ValidationPanel.vue'
import { getTrendTagType, getTrendClass, fmtNum } from '@/utils/format'

const props = defineProps<{ result: AnalysisResult }>()

const signalColor = computed(() => {
  const signal = props.result.trading_signal?.signal || ''
  if (signal.includes('buy')) return 'var(--color-up)'
  if (signal.includes('sell')) return 'var(--color-down)'
  return 'var(--color-warn)'
})

const signalBgClass = computed(() => {
  const signal = props.result.trading_signal?.signal || ''
  if (signal.includes('buy')) return 'signal-bull'
  if (signal.includes('sell')) return 'signal-bear'
  return 'signal-neutral'
})

const scorePercent = computed(() => {
  return Math.round((props.result.trading_signal?.score || 0) * 100)
})

const riskLevel = computed(() => {
  const r = props.result.validation?.risk_level || ''
  const map: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' }
  return map[r] || r || '未知'
})

const riskType = computed(() => {
  const r = props.result.validation?.risk_level || ''
  if (r === 'low') return 'success'
  if (r === 'high') return 'danger'
  return 'warning'
})

const trendState = computed(() => {
  const t = props.result.price_prediction?.day1?.trend || ''
  const map: Record<string, string> = {
    strong_up: '强势上涨',
    up: '上涨',
    neutral: '震荡',
    down: '下跌',
    strong_down: '强势下跌',
  }
  return map[t] || t || '未知'
})

const trendType = computed(() => {
  const t = props.result.price_prediction?.day1?.trend || ''
  if (t === 'strong_up' || t === 'up') return 'success'
  if (t === 'strong_down' || t === 'down') return 'danger'
  return 'warning'
})

const ps = computed<any>(() => props.result.position_strategy || ({} as any))

const isHeld = computed(() => 'avg_cost' in ps.value)

const profitBelowCost = computed(() => {
  return isHeld.value && ps.value.stop_profit_price != null && ps.value.avg_cost != null && ps.value.stop_profit_price < ps.value.avg_cost
})

const indicatorsExpanded = ref(false)
</script>

<template>
  <div class="report-panel">
    <div class="decision-section">
      <div class="signal-hero" :class="signalBgClass">
        <div class="signal-hero-left">
          <div class="signal-label">交易信号</div>
          <div class="signal-text" :style="{ color: signalColor }">
            {{ result.trading_signal?.signal_text || '持有' }}
          </div>
          <div class="signal-score">
            综合评分 <span class="score-val font-mono">{{ result.trading_signal?.score?.toFixed(3) || '0.500' }}</span>
          </div>
        </div>
        <el-progress
          type="dashboard"
          :percentage="scorePercent"
          :color="signalColor"
          :stroke-width="6"
          :width="72"
        />
      </div>

      <div class="decision-badges">
        <div class="badge-item">
          <span class="badge-label">风险等级</span>
          <el-tag :type="riskType" effect="dark" size="small">{{ riskLevel }}</el-tag>
        </div>
        <div class="badge-item">
          <span class="badge-label">趋势状态</span>
          <el-tag :type="trendType" effect="dark" size="small">{{ trendState }}</el-tag>
        </div>
        <div class="badge-item">
          <span class="badge-label">目标区间</span>
          <span class="badge-val font-mono">
            {{ fmtNum(result.price_prediction?.day1?.target_low) }} ~ {{ fmtNum(result.price_prediction?.day1?.target_high) }}
          </span>
        </div>
      </div>
    </div>

    <div class="strategy-section">
      <div class="section-label">持仓策略</div>
      <template v-if="isHeld">
        <div class="strat-grid">
          <div class="strat-item">
            <span class="strat-label">成本</span>
            <span class="strat-val font-mono">{{ fmtNum(ps.avg_cost) }}</span>
          </div>
          <div class="strat-item">
            <span class="strat-label">盈亏</span>
            <span
              class="strat-val font-mono"
              :class="(ps.price_change_pct || 0) >= 0 ? 'profit' : 'loss'"
            >
              {{ fmtNum(ps.price_change_pct) }}%
            </span>
          </div>
          <div class="strat-item">
            <span class="strat-label">{{ profitBelowCost ? '目标' : '止盈' }}</span>
            <span
              class="strat-val font-mono"
              :class="profitBelowCost ? 'warn' : 'profit'"
            >
              {{ fmtNum(ps.stop_profit_price) }}
            </span>
          </div>
          <div class="strat-item">
            <span class="strat-label">止损</span>
            <span class="strat-val loss font-mono">{{ fmtNum(ps.stop_loss_price) }}</span>
          </div>
        </div>
        <div class="strat-action">
          <el-tag
            :type="ps.position_adjust?.includes('减仓') ? 'danger' : ps.position_adjust?.includes('加仓') || ps.position_adjust?.includes('补仓') ? 'success' : 'warning'"
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
              :type="ps.buy_timing?.includes('不建议') ? 'danger' : ps.buy_timing?.includes('建议') || ps.buy_timing?.includes('可考虑') ? 'success' : 'warning'"
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
            <span class="strat-val loss font-mono">{{ fmtNum(ps.stop_loss_price) }}</span>
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

    <ValidationPanel v-if="result.validation" :validation="result.validation" />

    <div class="indicators-section">
      <div class="indicators-toggle" @click="indicatorsExpanded = !indicatorsExpanded">
        <span class="section-label">技术指标详情</span>
        <el-icon :class="{ expanded: indicatorsExpanded }"><ArrowRight /></el-icon>
      </div>
      <div v-show="indicatorsExpanded" class="indicators-content">
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
              DIF {{ fmtNum(result.indicators.MACD.latest.DIF) }} / DEA {{ fmtNum(result.indicators.MACD.latest.DEA) }}
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
            <span class="ind-detail font-mono">{{ fmtNum(result.indicators.RSI['RSI(12)']?.latest) }}</span>
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
              K {{ fmtNum(result.indicators.KDJ.latest.K) }} D {{ fmtNum(result.indicators.KDJ.latest.D) }} J {{ fmtNum(result.indicators.KDJ.latest.J) }}
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
            <span class="ind-detail font-mono">带宽 {{ fmtNum(result.indicators.BOLL.latest.bandwidth) }}%</span>
          </div>
        </div>
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

.decision-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.signal-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-up);
  transition: var(--transition-base);
}

.signal-hero:hover {
  border-color: var(--border-active);
}

.signal-hero.signal-bull {
  border-left-color: var(--color-up);
}

.signal-hero.signal-bear {
  border-left-color: var(--color-down);
}

.signal-hero.signal-neutral {
  border-left-color: var(--color-warn);
}

.signal-hero-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.signal-label {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.signal-text {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.signal-score {
  font-size: 12px;
  color: var(--text-muted);
}

.score-val {
  font-weight: 700;
  color: var(--text-primary);
}

.decision-badges {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.badge-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.badge-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.badge-val {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.strategy-section {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: var(--transition-base);
}

.strategy-section:hover {
  border-color: var(--border-active);
}

.section-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 12px;
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

.indicators-section {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: var(--transition-base);
}

.indicators-section:hover {
  border-color: var(--border-active);
}

.indicators-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.indicators-toggle .el-icon {
  transition: transform 0.2s ease;
  color: var(--text-muted);
  font-size: 12px;
}

.indicators-toggle .el-icon.expanded {
  transform: rotate(90deg);
}

.indicators-content {
  padding: 0 16px 16px;
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
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
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

@media (max-width: 768px) {
  .signal-text {
    font-size: 22px;
  }
  .decision-badges {
    flex-direction: column;
    gap: 8px;
  }
  .indicators-row {
    flex-direction: column;
  }
  .ind-chip {
    justify-content: space-between;
  }
}
</style>
