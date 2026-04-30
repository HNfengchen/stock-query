<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBacktestStore } from '@/stores/backtestStore'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import type { BacktestRequest } from '@/types'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

const store = useBacktestStore()

const form = ref<BacktestRequest>({
  stock_code: '',
  mode: 'builtin',
  params: {
    atr_multiplier: 1.5,
    lookback_days: 60,
  },
})

const customCode = ref(`def signal(df, indicators):
    """
    df: DataFrame - 历史K线数据
    indicators: dict - 技术指标
    返回: 'buy' | 'sell' | 'hold'
    """
    macd = indicators.get('MACD', {})
    rsi = indicators.get('RSI', {}).get('RSI(12)', {})

    if macd.get('signal') == '金叉' and rsi.get('signal') != '超买':
        return 'buy'
    elif macd.get('signal') == '死叉':
        return 'sell'
    return 'hold'
`)

const activeTab = ref('builtin')

const equityOption = computed(() => {
  if (!store.result?.equity_curve?.length) return {}
  const dates = store.result.equity_curve.map(d => d.date)
  const values = store.result.equity_curve.map(d => d.value)
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(20,27,45,0.95)',
      borderColor: 'rgba(0,212,170,0.3)',
      textStyle: { color: '#e0e6ed' },
      formatter: (params: any[]) => {
        const p = params[0]
        return `<div style="font-weight:600">${p.axisValue}</div><div>权益: ${p.value.toFixed(4)}</div>`
      },
    },
    grid: { left: 56, right: 16, top: 24, bottom: 48 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
      axisLabel: { color: '#8b92a8', fontSize: 10, rotate: 45 },
      axisTick: { show: false },
    },
    yAxis: {
      axisLine: { show: false },
      axisLabel: { color: '#8b92a8', fontSize: 10, inside: true, margin: 0 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisTick: { show: false },
    },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      lineStyle: { color: '#00d4aa', width: 2 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(0,212,170,0.3)' },
            { offset: 1, color: 'rgba(0,212,170,0)' },
          ],
        },
      },
      symbol: 'none',
    }],
  }
})

async function runBacktest() {
  const data: BacktestRequest = {
    stock_code: form.value.stock_code,
    mode: activeTab.value as 'builtin' | 'custom',
  }
  if (activeTab.value === 'builtin') {
    data.params = form.value.params
  } else {
    data.algorithm_code = customCode.value
    data.algorithm_name = 'custom_strategy'
  }
  try {
    await store.executeBacktest(data)
  } catch (e) {
    console.error(e)
  }
}

function exportCSV() {
  if (!store.result?.predictions?.length) return
  const headers = ['日期', '趋势', '预测区间低', '预测区间高', '实际价', '是否命中']
  const rows = store.result.predictions.map(p => [
    p.date, p.trend, p.predicted_low, p.predicted_high, p.actual_price, p.hit ? '是' : '否',
  ])
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `backtest_${store.result.stock_code}.csv`
  link.click()
}
</script>

<template>
  <div class="backtest-view">
    <h2 class="page-title">回测中心</h2>

    <div class="backtest-layout">
      <!-- 左侧配置 -->
      <div class="config-panel">
        <el-tabs v-model="activeTab" class="dark-tabs">
          <el-tab-pane label="内置策略" name="builtin">
            <div class="config-form">
              <el-form label-position="top">
                <el-form-item label="股票代码">
                  <el-input v-model="form.stock_code" placeholder="如 603956" />
                </el-form-item>
                <el-form-item label="ATR乘数">
                  <el-input-number v-model="form.params!.atr_multiplier" :precision="1" :step="0.1" :min="0.1" />
                </el-form-item>
                <el-form-item label="回看天数">
                  <el-input-number v-model="form.params!.lookback_days" :step="5" :min="10" :max="252" />
                </el-form-item>
              </el-form>
            </div>
          </el-tab-pane>
          <el-tab-pane label="自定义算法" name="custom">
            <div class="config-form">
              <el-form label-position="top">
                <el-form-item label="股票代码">
                  <el-input v-model="form.stock_code" placeholder="如 603956" />
                </el-form-item>
                <el-form-item label="算法代码 (Python)">
                  <el-input v-model="customCode" type="textarea" :rows="16" class="code-editor" />
                </el-form-item>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>
        <el-button type="primary" class="run-btn" :loading="store.loading" @click="runBacktest">
          <el-icon><VideoPlay /></el-icon> 开始回测
        </el-button>
      </div>

      <!-- 右侧结果 -->
      <div class="result-panel">
        <div v-if="store.error" class="error-message">
          <el-icon><Warning /></el-icon>
          <span>{{ store.error }}</span>
        </div>

        <div v-else-if="store.result" class="result-content">
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-label">Day1命中率</span>
              <span class="stat-value">{{ (store.result.statistics.day1_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day2命中率</span>
              <span class="stat-value">{{ (store.result.statistics.day2_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day1趋势准确率</span>
              <span class="stat-value">{{ (store.result.statistics.day1_trend_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day2趋势准确率</span>
              <span class="stat-value">{{ (store.result.statistics.day2_trend_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">夏普比率</span>
              <span class="stat-value">{{ store.result.statistics.sharpe_ratio.toFixed(2) }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">最大回撤</span>
              <span class="stat-value loss">{{ (store.result.statistics.max_drawdown * 100).toFixed(1) }}%</span>
            </div>
          </div>

          <div class="equity-chart">
            <div class="chart-header">
              <span class="chart-title">权益曲线</span>
              <el-button size="small" text @click="exportCSV">
                <el-icon><Download /></el-icon> 导出CSV
              </el-button>
            </div>
            <v-chart class="chart" :option="equityOption" autoresize />
          </div>

          <div class="predictions-table">
            <div class="chart-title">逐日预测明细</div>
            <el-table :data="store.result.predictions.slice(0, 20)" size="small" class="dark-table">
              <el-table-column prop="date" label="日期" width="120" />
              <el-table-column prop="trend" label="趋势" width="80" />
              <el-table-column label="预测区间" width="140">
                <template #default="{ row }">
                  {{ (row.predicted_low ?? 0).toFixed(2) }} ~ {{ (row.predicted_high ?? 0).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column prop="actual_price" label="实际价" width="100">
                <template #default="{ row }">
                  {{ row.actual_price != null ? row.actual_price.toFixed(2) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="hit" label="命中" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.hit ? 'success' : 'danger'" size="small" effect="dark">
                    {{ row.hit ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div v-else class="empty-state">
          <el-icon class="empty-icon"><DataAnalysis /></el-icon>
          <h3>配置参数并开始回测</h3>
          <p>选择内置策略或编写自定义算法进行回测验证</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backtest-view {
  max-width: 1600px;
  margin: 0 auto;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #e0e6ed;
  margin-bottom: 24px;
}

.backtest-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
}

.config-panel {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 16px;
  padding: 20px;
}

.config-form {
  margin-bottom: 16px;
}

.code-editor :deep(.el-textarea__inner) {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  background: rgba(0, 0, 0, 0.3);
  border-color: rgba(255, 255, 255, 0.1);
  color: #e0e6ed;
}

.run-btn {
  width: 100%;
  background: linear-gradient(135deg, #00d4aa 0%, #00a8e8 100%);
  border: none;
  font-weight: 600;
  height: 44px;
}

.run-btn:hover {
  background: linear-gradient(135deg, #00e8bc 0%, #00b8f8 100%);
}

.result-panel {
  min-height: 600px;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: rgba(255, 71, 87, 0.1);
  border: 1px solid rgba(255, 71, 87, 0.3);
  border-radius: 12px;
  color: #ff4757;
}

.result-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.stat-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-label {
  font-size: 12px;
  color: #8b92a8;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #00d4aa;
}

.stat-value.loss {
  color: #ff4757;
}

.equity-chart {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 12px;
  padding: 16px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e6ed;
  padding-left: 8px;
  border-left: 3px solid #00d4aa;
}

.chart {
  width: 100%;
  height: 300px;
}

.predictions-table {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 12px;
  padding: 16px;
}

.dark-table :deep(.el-table) {
  background: transparent;
}

.dark-table :deep(.el-table__header-wrapper th) {
  background: rgba(255, 255, 255, 0.03);
  color: #8b92a8;
}

.dark-table :deep(.el-table__row) {
  background: transparent;
  color: #e0e6ed;
}

.dark-table :deep(.el-table__row:hover td) {
  background: rgba(255, 255, 255, 0.03);
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

.dark-tabs :deep(.el-tabs__item) {
  color: #8b92a8;
}

.dark-tabs :deep(.el-tabs__item.is-active) {
  color: #00d4aa;
}

.dark-tabs :deep(.el-tabs__active-bar) {
  background-color: #00d4aa;
}

@media (max-width: 1200px) {
  .backtest-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
