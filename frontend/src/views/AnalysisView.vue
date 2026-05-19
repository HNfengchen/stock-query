<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStockStore } from '@/stores/stockStore'
import { useAsyncState } from '@/composables/useAsyncState'
import StockInput from '@/components/StockInput.vue'
import KlineChart from '@/components/KlineChart.vue'
import TechnicalChart from '@/components/TechnicalChart.vue'
import FundFlowChart from '@/components/FundFlowChart.vue'
import ReportPanel from '@/components/ReportPanel.vue'
import MarketStatusPanel from '@/components/MarketStatusPanel.vue'
import RiskCenter from '@/components/RiskCenter.vue'
import PredictionCenter from '@/components/PredictionCenter.vue'
import ValidationPanel from '@/components/ValidationPanel.vue'
import AnalysisLogPanel from '@/components/AnalysisLogPanel.vue'
import type { AnalysisRequest, AnalysisResult, StockInfo } from '@/types'
import { fmtNum, fmtMarketCap, fmtVolume } from '@/utils/format'
import { getCachedAnalysis } from '@/api/analysis'
import { getLogger } from '@/utils/logger'

const logger = getLogger('AnalysisView')

const route = useRoute()
const store = useStockStore()
const analysisState = useAsyncState<AnalysisResult>()

const form = ref<AnalysisRequest>({
  stock_input: '',
  position_status: '未持有',
  cost_price: undefined,
})

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const logPanelRef = ref<InstanceType<typeof AnalysisLogPanel> | null>(null)

watch(() => store.loading, (val) => {
  if (val) {
    nextTick(() => {
      logPanelRef.value?.expand()
    })
  }
})

// 关键：当 store 层已完成（loading=false + currentResult有值）但 analysisState 还在 loading 时，
// 立即同步 analysisState 为 success，确保报告立即显示
watch(
  () => [store.loading, store.currentResult] as const,
  ([isLoading, result]) => {
    if (!isLoading && result && analysisState.isLoading.value) {
      analysisState.toSuccess(result)
    }
  },
)

let lastAnalyzedCode = ''
let lastAnalyzedPosition = ''
let lastAnalyzedCost = ''

watch(
  () => [route.query.code, route.query.position, route.query.cost] as const,
  async ([code, position, cost]) => {
    if (!code) return
    const sCode = String(code)
    const sPosition = String(position ?? '')
    const sCost = String(cost ?? '')
    if (sCode === lastAnalyzedCode && sPosition === lastAnalyzedPosition && sCost === lastAnalyzedCost) return
    lastAnalyzedCode = sCode
    lastAnalyzedPosition = sPosition
    lastAnalyzedCost = sCost
    form.value.stock_input = sCode
    form.value.position_status = (sPosition || '未持有') as '已持有' | '未持有'
    form.value.cost_price = sCost ? parseFloat(sCost) : undefined

    // 先查缓存，命中则直接显示结果
    try {
      const cacheResult = await getCachedAnalysis(sCode, sPosition || '未持有', sCost ? parseFloat(sCost) : undefined)
      logger.info(`缓存查询: code=${sCode}, cached=${cacheResult.cached}, age=${cacheResult.age_seconds}s`)
      if (cacheResult.cached && cacheResult.result) {
        store.setAnalysisResult(cacheResult.result)
        analysisState.toSuccess(cacheResult.result)
        return
      }
    } catch (e) {
      logger.warn('缓存查询失败，继续正常分析:', e)
    }

    doAnalyze()
  },
  { immediate: true },
)

async function doAnalyze() {
  const stockInput = form.value.stock_input.trim()
  if (!stockInput) {
    ElMessage.warning('请输入股票代码或名称')
    return
  }
  if (store.loading) {
    store.cancelAnalysis()
  }
  store.clearLogs()
  analysisState.toLoading()
  try {
    await store.runAnalysis(form.value)
    if (store.currentResult) {
      analysisState.toSuccess(store.currentResult)
    } else {
      analysisState.toError('分析未返回结果，请稍后重试')
    }
    await store.loadWatchlist()
  } catch (e: any) {
    // 如果 stage_complete 已收到（currentResult 不为空），仍显示报告
    if (store.currentResult) {
      analysisState.toSuccess(store.currentResult)
    } else {
      const message = e?.message || '分析失败，请稍后重试'
      analysisState.toError(message)
      ElMessage.error(message)
    }
  }
}

function handleAnalyze() {
  lastAnalyzedCode = form.value.stock_input
  lastAnalyzedPosition = form.value.position_status
  lastAnalyzedCost = String(form.value.cost_price ?? '')
  doAnalyze()
}

function handleCancel() {
  store.cancelAnalysis()
  // 如果已有结果，取消只停止loading，保留报告显示
  if (store.currentResult) {
    analysisState.toSuccess(store.currentResult)
  } else {
    analysisState.reset()
  }
}

async function addToWatchlist() {
  if (!store.currentResult) return
  try {
    await store.addStock({
      stock_input: store.currentResult.stock_code,
      position_status: form.value.position_status,
      cost_price: form.value.cost_price,
    })
    ElMessage.success('已加入历史列表')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  }
}

const si = computed<StockInfo>(() => store.currentResult?.stock_info ?? {})

const changePct = computed(() => {
  const v = Number(si.value['涨跌幅'])
  return isNaN(v) ? null : v
})

const changeAmt = computed(() => {
  const v = Number(si.value['涨跌额'])
  return isNaN(v) ? null : v
})

const emptyKline = {
  dates: [], opens: [], closes: [], highs: [], lows: [], volumes: [],
  ma5: [], ma10: [], ma20: [], ma60: [], boll_upper: [], boll_middle: [], boll_lower: [],
}

const emptyTechnical = {
  dates: [], macd: [], dif: [], dea: [], rsi6: [], rsi12: [], k: [], d: [], j: [],
}

const emptyFundFlow = {
  dates: [], main_flow: [], main_flow_ratio: [], small_flow: [], change_pct: [],
}

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    stage_basic: '基础数据',
    stage_technical: '技术指标',
    stage_risk: '风险评估',
    stage_prediction: '预测分析',
    stage_complete: '完成',
  }
  return map[stage] || stage
}
</script>

<template>
  <div class="analysis-view">
    <StockInput v-model="form" :loading="analysisState.isLoading.value" @analyze="handleAnalyze" @cancel="handleCancel" />

    <div v-if="analysisState.isLoading.value" class="log-section">
      <div class="loading-indicator">
        <div class="loading-spinner">
          <div class="spinner-ring" />
          <div class="spinner-ring" />
          <div class="spinner-ring" />
        </div>
        <span class="loading-text">正在分析中...</span>
        <span v-if="store.streamStage" class="loading-stage">{{ stageLabel(store.streamStage) }}</span>
      </div>
      <AnalysisLogPanel ref="logPanelRef" :logs="store.analysisLogs" />
    </div>

    <div v-else-if="analysisState.isError.value" class="error-section">
      <div class="error-card">
        <el-icon class="error-icon"><WarningFilled /></el-icon>
        <div class="error-content">
          <h3>分析失败</h3>
          <p>{{ analysisState.error.value }}</p>
        </div>
        <el-button type="primary" size="small" @click="handleAnalyze">
          <el-icon><RefreshRight /></el-icon>
          <span>重试</span>
        </el-button>
      </div>
      <AnalysisLogPanel v-if="store.analysisLogs.length > 0" ref="logPanelRef" :logs="store.analysisLogs" />
    </div>

    <div v-if="analysisState.isSuccess.value && store.currentResult" class="result-container">
      <div class="stock-header">
        <div class="header-top">
          <div class="stock-info">
            <div class="stock-main">
              <span class="stock-name">{{ store.currentResult.stock_name }}</span>
              <span class="stock-code">{{ store.currentResult.stock_code }}</span>
            </div>
            <div v-if="store.currentResult.price_prediction?.current != null" class="stock-price-row">
              <span class="current-price font-mono">
                {{ store.currentResult.price_prediction.current.toFixed(2) }}
              </span>
              <span class="price-unit">CNY</span>
              <span
                v-if="changePct !== null"
                class="price-change"
                :class="changePct >= 0 ? 'up' : 'down'"
              >
                {{ changePct >= 0 ? '+' : '' }}{{ changePct.toFixed(2) }}%
                <template v-if="changeAmt !== null">
                  ({{ changeAmt >= 0 ? '+' : '' }}{{ changeAmt.toFixed(2) }})
                </template>
              </span>
            </div>
          </div>
          <el-button
            type="primary"
            size="small"
            text
            class="add-btn"
            @click="addToWatchlist"
          >
            <el-icon><Plus /></el-icon>
            <span>加入列表</span>
          </el-button>
        </div>

        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">今开</span>
            <span class="metric-value font-mono">{{ fmtNum(si['今开']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">昨收</span>
            <span class="metric-value font-mono">{{ fmtNum(si['昨收']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">最高</span>
            <span class="metric-value font-mono up">{{ fmtNum(si['最高']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">最低</span>
            <span class="metric-value font-mono down">{{ fmtNum(si['最低']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">振幅</span>
            <span class="metric-value font-mono">{{ fmtNum(si['振幅']) }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">换手率</span>
            <span class="metric-value font-mono">{{ fmtNum(si['换手率']) }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">成交额</span>
            <span class="metric-value font-mono">{{ fmtVolume(si['成交额']) }}</span>
          </div>
          <div class="metric-divider" />
          <div class="metric-item">
            <span class="metric-label">市盈率(动)</span>
            <span class="metric-value font-mono">{{ fmtNum(si['市盈率-动态']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">市净率</span>
            <span class="metric-value font-mono">{{ fmtNum(si['市净率']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">总市值</span>
            <span class="metric-value font-mono">{{ fmtMarketCap(si['总市值']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">流通市值</span>
            <span class="metric-value font-mono">{{ fmtMarketCap(si['流通市值']) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">所属行业</span>
            <span class="metric-value industry">{{ si['所属行业'] || '-' }}</span>
          </div>
        </div>
      </div>

      <div class="cockpit-layout">
        <aside class="cockpit-left" :class="{ collapsed: leftCollapsed }">
          <div class="sidebar-toggle" @click="leftCollapsed = !leftCollapsed">
            <el-icon :class="{ flipped: leftCollapsed }"><DArrowLeft /></el-icon>
          </div>
          <div v-show="!leftCollapsed" class="sidebar-content">
            <MarketStatusPanel :status="store.marketStatus" />
          </div>
        </aside>

        <main class="cockpit-center">
          <ReportPanel :result="store.currentResult" />
          <PredictionCenter :prediction="store.predictionResult" />

          <div class="charts-grid">
            <div class="chart-card chart-main">
              <div class="chart-header">
                <span class="chart-title">K 线走势</span>
                <div class="chart-legend">
                  <span class="legend-item up"><span class="legend-dot" />涨</span>
                  <span class="legend-item down"><span class="legend-dot" />跌</span>
                </div>
              </div>
              <KlineChart :data="store.currentResult.charts?.kline || emptyKline" />
            </div>
            <div class="chart-card">
              <div class="chart-header">
                <span class="chart-title">技术指标</span>
              </div>
              <TechnicalChart :data="store.currentResult.charts?.technical || emptyTechnical" />
            </div>
            <div class="chart-card">
              <div class="chart-header">
                <span class="chart-title">资金流向</span>
              </div>
              <FundFlowChart :data="store.currentResult.charts?.fund_flow || emptyFundFlow" />
            </div>
          </div>
        </main>

        <aside class="cockpit-right" :class="{ collapsed: rightCollapsed }">
          <div class="sidebar-toggle" @click="rightCollapsed = !rightCollapsed">
            <el-icon :class="{ flipped: rightCollapsed }"><DArrowRight /></el-icon>
          </div>
          <div v-show="!rightCollapsed" class="sidebar-content">
            <RiskCenter :risk="store.riskAssessment" />
            <ValidationPanel
              v-if="store.currentResult.validation"
              :validation="store.currentResult.validation"
              class="right-validation"
            />
          </div>
        </aside>
      </div>
    </div>

    <div v-if="analysisState.isIdle.value" class="empty-state">
      <div class="empty-icon">
        <el-icon><TrendCharts /></el-icon>
      </div>
      <h3>输入股票代码开始分析</h3>
      <p>支持股票代码或名称搜索，如 603956 或 威派格</p>
    </div>
  </div>
</template>

<style scoped>
.analysis-view {
  max-width: 1600px;
  margin: 0 auto;
}

.log-section {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 16px 20px;
  gap: 12px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.loading-spinner {
  position: relative;
  width: 48px;
  height: 48px;
}

.spinner-ring {
  position: absolute;
  border: 2px solid transparent;
  border-top-color: var(--color-up, #26a69a);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-ring:nth-child(1) {
  inset: 0;
  animation-duration: 1.2s;
}

.spinner-ring:nth-child(2) {
  inset: 6px;
  border-top-color: var(--color-accent, #42a5f5);
  animation-duration: 0.9s;
  animation-direction: reverse;
}

.spinner-ring:nth-child(3) {
  inset: 12px;
  border-top-color: var(--color-warn, #ffa726);
  animation-duration: 0.6s;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-size: 14px;
}

.loading-stage {
  font-size: 12px;
  color: var(--color-up, #26a69a);
  padding: 2px 10px;
  background: rgba(0, 212, 170, 0.08);
  border-radius: 10px;
  font-weight: 500;
}

.error-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
}

.error-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(255, 71, 87, 0.06);
  border: 1px solid rgba(255, 71, 87, 0.15);
  border-radius: var(--radius-md, 10px);
}

.error-icon {
  font-size: 32px;
  color: var(--color-down, #ef5350);
  flex-shrink: 0;
}

.error-content {
  flex: 1;
  min-width: 0;
}

.error-content h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-down, #ef5350);
  margin-bottom: 4px;
}

.error-content p {
  font-size: 13px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.result-container {
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.stock-header {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stock-info {
  display: flex;
  align-items: center;
  gap: 24px;
}

.stock-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stock-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.stock-code {
  font-size: 13px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.stock-price-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.current-price {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-up, #26a69a);
  letter-spacing: -0.03em;
}

.price-unit {
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.price-change {
  font-size: 13px;
  font-weight: 600;
  margin-left: 4px;
}

.price-change.up {
  color: var(--color-up, #26a69a);
}

.price-change.down {
  color: var(--color-down, #ef5350);
}

.add-btn {
  color: var(--color-up, #26a69a) !important;
  font-weight: 500;
}

.add-btn:hover {
  color: #4db6ac !important;
  background: rgba(0, 212, 170, 0.08) !important;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 0;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  padding-top: 12px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 4px;
  transition: background 0.15s;
}

.metric-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.metric-label {
  font-size: 10px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  letter-spacing: -0.01em;
}

.metric-value.up {
  color: var(--color-up, #26a69a);
}

.metric-value.down {
  color: var(--color-down, #ef5350);
}

.metric-value.industry {
  font-size: 12px;
  color: var(--color-accent, #42a5f5);
  font-family: inherit;
}

.metric-divider {
  grid-column: 1 / -1;
  height: 1px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.05));
  margin: 4px 0;
}

.cockpit-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.cockpit-left {
  width: 250px;
  flex-shrink: 0;
  position: sticky;
  top: 20px;
  display: flex;
  align-items: flex-start;
  transition: width 0.3s ease;
  overflow: hidden;
}

.cockpit-left.collapsed {
  width: 32px;
}

.cockpit-right {
  width: 300px;
  flex-shrink: 0;
  position: sticky;
  top: 20px;
  display: flex;
  align-items: flex-start;
  transition: width 0.3s ease;
  overflow: hidden;
}

.cockpit-right.collapsed {
  width: 32px;
}

.sidebar-toggle {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-size: 12px;
  flex-shrink: 0;
  transition: var(--transition-fast, 0.15s ease);
  z-index: 1;
}

.sidebar-toggle:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.sidebar-toggle .el-icon.flipped {
  transform: rotate(180deg);
}

.cockpit-left .sidebar-toggle {
  margin-right: 8px;
}

.cockpit-right .sidebar-toggle {
  margin-left: 8px;
  order: 1;
}

.sidebar-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cockpit-right .sidebar-content {
  order: 0;
}

.right-validation {
  margin-top: 0;
}

.cockpit-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

.chart-card {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  transition: var(--transition-base, 0.25s ease);
}

.chart-card:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.chart-main {
  min-height: 480px;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  letter-spacing: 0.03em;
}

.chart-legend {
  display: flex;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.legend-item.up .legend-dot {
  background: var(--color-up, #26a69a);
}

.legend-item.down .legend-dot {
  background: var(--color-down, #ef5350);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 20px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  text-align: center;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 20px;
  color: rgba(0, 212, 170, 0.2);
}

.empty-state h3 {
  font-size: 18px;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  margin-bottom: 8px;
  font-weight: 600;
}

.empty-state p {
  font-size: 13px;
}

@media (max-width: 1200px) {
  .cockpit-layout {
    flex-wrap: wrap;
  }

  .cockpit-left,
  .cockpit-right {
    width: 100%;
    position: static;
    order: 1;
  }

  .cockpit-center {
    width: 100%;
    order: 0;
  }

  .cockpit-left.collapsed,
  .cockpit-right.collapsed {
    width: 100%;
  }

  .sidebar-toggle {
    display: none;
  }

  .cockpit-left .sidebar-content,
  .cockpit-right .sidebar-content {
    display: flex !important;
  }

  .cockpit-right .sidebar-toggle {
    order: 0;
  }

  .cockpit-right .sidebar-content {
    order: 1;
  }
}

@media (max-width: 768px) {
  .header-top {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }
  .stock-info {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }
  .current-price {
    font-size: 24px;
  }
  .metrics-grid {
    grid-template-columns: repeat(4, 1fr);
  }
  .chart-main {
    min-height: 360px;
  }
}

@media (max-width: 480px) {
  .metrics-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
