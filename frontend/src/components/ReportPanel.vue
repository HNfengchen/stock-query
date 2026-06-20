<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AnalysisResult, PositionStrategyHeld, PositionStrategyNotHeld } from '@/types'
import { getTrendTagType, getTrendClass, fmtNum } from '@/utils/format'

const props = defineProps<{ result: AnalysisResult }>()

const signalColor = computed(() => {
  const signal = props.result.trading_signal?.signal || ''
  if (signal.includes('buy')) return 'var(--color-up, #26a69a)'
  if (signal.includes('sell')) return 'var(--color-down, #ef5350)'
  return 'var(--color-warn, #ffa726)'
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

const ps = computed<PositionStrategyHeld | PositionStrategyNotHeld>(() => props.result.position_strategy ?? ({} as PositionStrategyNotHeld))

const isHeld = computed(() => 'avg_cost' in ps.value && ps.value.avg_cost != null)

const heldPs = computed<PositionStrategyHeld>(() => isHeld.value ? ps.value as PositionStrategyHeld : ({} as PositionStrategyHeld))

const notHeldPs = computed<PositionStrategyNotHeld>(() => !isHeld.value ? ps.value as PositionStrategyNotHeld : ({} as PositionStrategyNotHeld))

const profitBelowCost = computed(() => {
  return isHeld.value && heldPs.value.stop_profit_price != null && heldPs.value.avg_cost != null && heldPs.value.stop_profit_price < heldPs.value.avg_cost
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
            <span class="strat-val font-mono">{{ fmtNum(heldPs.avg_cost) }}</span>
          </div>
          <div class="strat-item">
            <span class="strat-label">盈亏</span>
            <span
              class="strat-val font-mono"
              :class="(heldPs.price_change_pct || 0) >= 0 ? 'profit' : 'loss'"
            >
              {{ fmtNum(heldPs.price_change_pct) }}%
            </span>
          </div>
          <div class="strat-item">
            <span class="strat-label">{{ profitBelowCost ? '目标' : '止盈' }}</span>
            <span
              class="strat-val font-mono"
              :class="profitBelowCost ? 'warn' : 'profit'"
            >
              {{ fmtNum(heldPs.stop_profit_price) }}
            </span>
          </div>
          <div class="strat-item">
            <span class="strat-label">止损</span>
            <span class="strat-val loss font-mono">{{ fmtNum(heldPs.stop_loss_price) }}</span>
          </div>
        </div>
        <div class="strat-action">
          <el-tag
            :type="heldPs.position_adjust?.includes('减仓') ? 'danger' : heldPs.position_adjust?.includes('加仓') || heldPs.position_adjust?.includes('补仓') ? 'success' : 'warning'"
            effect="dark"
            size="small"
          >
            {{ heldPs.position_adjust }}
          </el-tag>
        </div>
      </template>
      <template v-else>
        <div class="strat-grid">
          <div class="strat-item">
            <span class="strat-label">时机</span>
            <el-tag
              :type="notHeldPs.buy_timing?.includes('不建议') ? 'danger' : notHeldPs.buy_timing?.includes('建议') || notHeldPs.buy_timing?.includes('可考虑') ? 'success' : 'warning'"
              effect="dark"
              size="small"
            >
              {{ notHeldPs.buy_timing }}
            </el-tag>
          </div>
          <div class="strat-item">
            <span class="strat-label">仓位</span>
            <span class="strat-val font-mono">
              {{ notHeldPs.position_size_label || (notHeldPs.position_size_pct != null ? notHeldPs.position_size_pct + '%' : '-') }}
            </span>
          </div>
          <div class="strat-item">
            <span class="strat-label">止损</span>
            <span class="strat-val loss font-mono">{{ fmtNum(notHeldPs.stop_loss_price) }}</span>
          </div>
          <div class="strat-item">
            <span class="strat-label">风险</span>
            <el-tag
              :type="notHeldPs.risk_level?.includes('低') ? 'success' : notHeldPs.risk_level?.includes('高') ? 'danger' : 'warning'"
              effect="dark"
              size="small"
            >
              {{ notHeldPs.risk_level }}
            </el-tag>
          </div>
        </div>
      </template>
    </div>

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
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  border-left: 3px solid var(--color-up, #26a69a);
  transition: var(--transition-base, 0.25s ease);
}

.signal-hero:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.signal-hero.signal-bull {
  border-left-color: var(--color-up, #26a69a);
}

.signal-hero.signal-bear {
  border-left-color: var(--color-down, #ef5350);
}

.signal-hero.signal-neutral {
  border-left-color: var(--color-warn, #ffa726);
}

.signal-hero-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.signal-label {
  font-size: 10px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.score-val {
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.decision-badges {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
}

.badge-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.badge-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.badge-val {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.strategy-section {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  transition: var(--transition-base, 0.25s ease);
}

.strategy-section:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.section-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  width: 36px;
  flex-shrink: 0;
  font-weight: 500;
}

.strat-val {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.strat-val.profit { color: var(--color-up, #26a69a); }
.strat-val.loss { color: var(--color-down, #ef5350); }
.strat-val.warn { color: var(--color-warn, #ffa726); }

.strat-action {
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.indicators-section {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  overflow: hidden;
  transition: var(--transition-base, 0.25s ease);
}

.indicators-section:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
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
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
  background: var(--bg-secondary, #1a1a1a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  border-radius: var(--radius-sm, 6px);
  transition: var(--transition-fast, 0.15s ease);
}

.ind-chip:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.ind-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  letter-spacing: 0.03em;
}

.ind-signal {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.ind-signal.bull { background: var(--color-up-dim, rgba(38, 166, 154, 0.15)); color: var(--color-up, #26a69a); }
.ind-signal.bear { background: var(--color-down-dim, rgba(239, 83, 80, 0.15)); color: var(--color-down, #ef5350); }
.ind-signal.neutral { background: rgba(245, 158, 11, 0.15); color: var(--color-warn, #ffa726); }

.ind-detail {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
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
