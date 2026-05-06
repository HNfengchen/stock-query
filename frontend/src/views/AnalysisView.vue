<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStockStore } from '@/stores/stockStore'
import StockInput from '@/components/StockInput.vue'
import KlineChart from '@/components/KlineChart.vue'
import TechnicalChart from '@/components/TechnicalChart.vue'
import FundFlowChart from '@/components/FundFlowChart.vue'
import ReportPanel from '@/components/ReportPanel.vue'
import type { AnalysisRequest } from '@/types'

const route = useRoute()
const store = useStockStore()

const form = ref<AnalysisRequest>({
  stock_input: '',
  position_status: '未持有',
  cost_price: null,
})

let lastAnalyzedCode = ''
let lastAnalyzedPosition = ''
let lastAnalyzedCost = ''

watch(
  () => [route.query.code, route.query.position, route.query.cost] as const,
  ([code, position, cost]) => {
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
    form.value.cost_price = sCost ? parseFloat(sCost) : null
    doAnalyze()
  },
  { immediate: true },
)

async function doAnalyze() {
  if (!form.value.stock_input.trim()) return
  try {
    await store.runAnalysis(form.value)
  } catch (e) {
    console.error(e)
  }
}

function handleAnalyze() {
  lastAnalyzedCode = form.value.stock_input
  lastAnalyzedPosition = form.value.position_status
  lastAnalyzedCost = String(form.value.cost_price ?? '')
  doAnalyze()
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

const emptyKline = {
  dates: [], opens: [], closes: [], highs: [], lows: [], volumes: [],
  ma5: [], ma10: [], ma20: [], ma60: [], boll_upper: [], boll_middle: [], boll_lower: [],
}

const emptyTechnical = {
  dates: [], macd: [], dif: [], dea: [], rsi6: [], rsi12: [], k: [], d: [], j: [],
}

const emptyFundFlow = {
  dates: [], main_flow: [], main_flow_ratio: [], retail_flow: [],
}
</script>

<template>
  <div class="analysis-view">
    <StockInput v-model="form" :loading="store.loading" @analyze="handleAnalyze" />

    <div v-if="store.loading" class="loading-state">
      <el-icon class="loading-icon"><Loading /></el-icon>
      <span>正在分析中，请稍候...</span>
    </div>

    <div v-else-if="store.hasResult && store.currentResult" class="result-container">
      <div class="result-header">
        <div class="stock-title">
          <span class="stock-code">{{ store.currentResult.stock_code }}</span>
          <span class="stock-name">{{ store.currentResult.stock_name }}</span>
          <span class="stock-price" v-if="store.currentResult.price_prediction?.current">
            ¥{{ store.currentResult.price_prediction.current.toFixed(2) }}
          </span>
        </div>
        <el-button type="primary" size="small" text @click="addToWatchlist">
          <el-icon><Plus /></el-icon> 加入历史列表
        </el-button>
      </div>

      <div class="info-section">
        <ReportPanel :result="store.currentResult" />
      </div>

      <div class="charts-section">
        <div class="chart-block">
          <div class="chart-block-title">K线图</div>
          <KlineChart :data="store.currentResult.charts?.kline || emptyKline" />
        </div>
        <div class="chart-block">
          <div class="chart-block-title">技术指标</div>
          <TechnicalChart :data="store.currentResult.charts?.technical || emptyTechnical" />
        </div>
        <div class="chart-block">
          <div class="chart-block-title">资金流向</div>
          <FundFlowChart :data="store.currentResult.charts?.fund_flow || emptyFundFlow" />
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <el-icon class="empty-icon"><TrendCharts /></el-icon>
      <h3>输入股票代码开始分析</h3>
      <p>支持股票代码或名称搜索，如 603956 或 威派格</p>
    </div>
  </div>
</template>

<style scoped>
.analysis-view {
  max-width: 1400px;
  margin: 0 auto;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #8b92a8;
  gap: 16px;
}

.loading-icon {
  font-size: 48px;
  animation: spin 1s linear infinite;
  color: #00d4aa;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.result-container {
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 4px;
}

.stock-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.stock-code {
  font-size: 24px;
  font-weight: 700;
  color: #00d4aa;
}

.stock-name {
  font-size: 18px;
  color: #8b92a8;
}

.stock-price {
  font-size: 20px;
  font-weight: 600;
  color: #e0e6ed;
  margin-left: 8px;
}

.info-section {
  margin-bottom: 24px;
}

.charts-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.chart-block {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 16px;
  padding: 20px;
}

.chart-block-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e6ed;
  margin-bottom: 16px;
  padding-left: 10px;
  border-left: 3px solid #00d4aa;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 20px;
  color: #8b92a8;
  text-align: center;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 24px;
  color: rgba(0, 212, 170, 0.3);
}

.empty-state h3 {
  font-size: 20px;
  color: #e0e6ed;
  margin-bottom: 8px;
}

.empty-state p {
  font-size: 14px;
}

@media (max-width: 768px) {
  .result-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }
  .stock-title {
    flex-wrap: wrap;
  }
  .chart-block {
    padding: 12px;
    border-radius: 12px;
  }
  .charts-section {
    gap: 16px;
  }
}
</style>
