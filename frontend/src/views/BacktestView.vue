<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBacktestStore } from '@/stores/backtestStore'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent } from 'echarts/components'
import type { BacktestRequest } from '@/types'
import { TREND_LABEL_MAP, getTrendColor, getTrendTagType, getTrendClass, trendToValue, changeToTrendValue } from '@/utils/format'

use([CanvasRenderer, LineChart, BarChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent])

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
    df: DataFrame - K线数据，列名: opens, closes, highs, lows, volumes
    indicators: dict - 技术指标，含 latest 和 signal 字段
    返回: 'buy' | 'sell' | 'hold'
    """
    if len(df) < 5:
        return 'hold'

    closes = df['closes'].values
    volumes = df['volumes'].values

    last_close = closes[-1]
    prev_close = closes[-2]
    avg_vol_5 = sum(volumes[-5:]) / 5
    last_vol = volumes[-1]

    ma5 = sum(closes[-5:]) / 5
    ma3 = sum(closes[-3:]) / 3

    price_up = last_close > prev_close
    vol_up = last_vol > avg_vol_5 * 1.2
    above_ma5 = last_close > ma5
    below_ma5 = last_close < ma5

    if price_up and vol_up and above_ma5 and prev_close <= ma5:
        return 'buy'
    if last_close < ma3 and prev_close >= ma3:
        return 'sell'
    return 'hold'
`)

const activeTab = ref('builtin')
const currentPage = ref(1)
const pageSize = ref(20)

const priceCompareOption = computed(() => {
  if (!store.result?.predictions?.length) return {}
  const preds = store.result.predictions
  const dates = preds.map(p => p.date)
  const actualPrices = preds.map(p => p.actual_price)

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10, 14, 26, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.2)',
      textStyle: { color: '#f1f5f9', fontSize: 11 },
      formatter: (params: any[]) => {
        const idx = params[0]?.dataIndex
        if (idx === undefined || idx < 0) return ''
        const p = preds[idx]
        if (!p) return ''
        let html = `<div style="font-weight:600;margin-bottom:6px">${p.date}</div>`
        const tColor = getTrendColor(p.trend)
        html += `<div>预测趋势: <span style="color:${tColor}">${TREND_LABEL_MAP[p.trend] || p.trend}</span></div>`
        html += `<div>预测区间: <span class="font-mono">${p.predicted_low.toFixed(2)} ~ ${p.predicted_high.toFixed(2)}</span></div>`
        if (p.current_price != null) {
          html += `<div>当日收盘: <span class="font-mono">${p.current_price.toFixed(2)}</span></div>`
        }
        if (p.actual_price != null) {
          html += `<div>次日实际: <span style="color:var(--color-accent);font-weight:600">${p.actual_price.toFixed(2)}</span></div>`
          if (p.current_price != null) {
            const chg = ((p.actual_price - p.current_price) / p.current_price * 100).toFixed(2)
            html += `<div>涨跌幅: <span style="color:${parseFloat(chg) >= 0 ? 'var(--color-up)' : 'var(--color-down)'}">${chg}%</span></div>`
          }
          html += `<div>命中: <span style="color:${p.hit ? 'var(--color-up)' : 'var(--color-down)'}">${p.hit ? '是' : '否'}</span></div>`
        }
        return html
      },
    },
    legend: {
      data: ['预测区间', '实际价格'],
      textStyle: { color: 'var(--text-muted)', fontSize: 11 },
      top: 4,
    },
    grid: { left: 56, right: 16, top: 40, bottom: 56 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: '#475569', fontSize: 9, rotate: 45, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: {
      scale: true,
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, inside: false, margin: 8, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)', type: [4, 4] } },
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: '预测区间',
        type: 'custom',
        renderItem: (_params: any, api: any) => {
          const x = api.coord([api.value(0), 0])[0]
          const yLow = api.coord([0, api.value(1)])[1]
          const yHigh = api.coord([0, api.value(2)])[1]
          const width = 12
          const hit = api.value(3)
          return {
            type: 'rect',
            shape: { x: x - width / 2, y: yHigh, width, height: yLow - yHigh },
            style: {
              fill: hit ? 'rgba(0, 212, 170, 0.2)' : 'rgba(255, 71, 87, 0.2)',
              stroke: hit ? 'var(--color-up)' : 'var(--color-down)',
              lineWidth: 1,
            },
          }
        },
        data: preds.map((p, i) => [i, p.predicted_low, p.predicted_high, p.hit]),
        z: 1,
      },
      {
        name: '实际价格',
        type: 'line',
        data: actualPrices,
        smooth: true,
        lineStyle: { color: 'var(--color-accent)', width: 2 },
        symbol: 'circle',
        symbolSize: 5,
        itemStyle: { color: 'var(--color-accent)', borderWidth: 0 },
        z: 2,
      },
    ],
  }
})

const trendAccuracyOption = computed(() => {
  if (!store.result?.predictions?.length) return {}
  const preds = store.result.predictions
  const dates = preds.map(p => p.date)

  const trendValues = preds.map(p => trendToValue(p.trend))

  const actualTrendValues = preds.map(p => {
    if (p.actual_price == null || p.current_price == null) return null
    const change = (p.actual_price - p.current_price) / p.current_price
    return changeToTrendValue(change)
  })

  const matchData: number[] = []
  for (let i = 0; i < preds.length; i++) {
    if (actualTrendValues[i] === null) {
      matchData.push(NaN)
    } else {
      matchData.push(trendValues[i] === actualTrendValues[i] ? 1 : 0)
    }
  }

  const hitRate = matchData.filter(v => !isNaN(v))
  const correctCount = hitRate.filter(v => v === 1).length
  const totalValid = hitRate.length
  const accuracyPct = totalValid > 0 ? (correctCount / totalValid * 100).toFixed(1) : '0'

  return {
    backgroundColor: 'transparent',
    title: {
      text: `趋势准确率: ${accuracyPct}%`,
      textStyle: { color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 },
      left: 8,
      top: 4,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10, 14, 26, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.2)',
      textStyle: { color: '#f1f5f9', fontSize: 11 },
      formatter: (params: any[]) => {
        const idx = params[0]?.dataIndex
        if (idx === undefined || idx < 0) return ''
        const p = preds[idx]
        if (!p) return ''
        let html = `<div style="font-weight:600;margin-bottom:4px">${p.date}</div>`
        html += `<div>预测: <span style="color:${getTrendColor(p.trend)}">${TREND_LABEL_MAP[p.trend] || p.trend}</span></div>`
        const actualVal = actualTrendValues[idx]
        if (actualVal !== null && actualVal !== undefined) {
          const actualName = actualVal === 2 ? '大幅上涨' : actualVal === 1 ? '上涨' : actualVal === -1 ? '下跌' : actualVal === -2 ? '大幅下跌' : '震荡'
          html += `<div>实际: <span style="color:${getTrendColor(actualVal === 2 ? 'strong_up' : actualVal === 1 ? 'up' : actualVal === -1 ? 'down' : actualVal === -2 ? 'strong_down' : 'neutral')}">${actualName}</span></div>`
        }
        const matchVal = matchData[idx]
        if (matchVal !== undefined && !isNaN(matchVal)) {
          html += `<div>正确: <span style="color:${matchVal ? 'var(--color-up)' : 'var(--color-down)'}">${matchVal ? '是' : '否'}</span></div>`
        }
        return html
      },
    },
    grid: { left: 40, right: 16, top: 40, bottom: 56 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: '#475569', fontSize: 9, rotate: 45, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: {
      min: -0.5,
      max: 1.5,
      axisLine: { show: false },
      axisLabel: {
        color: '#475569',
        fontSize: 10,
        fontFamily: 'SF Mono, JetBrains Mono, monospace',
        formatter: (v: number) => v <= 0 ? '错误' : '正确',
      },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)', type: [4, 4] } },
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [{
      type: 'bar',
      data: matchData.map((v, i) => ({
        value: isNaN(v) ? null : v,
        itemStyle: {
          color: v === 1 ? 'var(--color-up)' : v === 0 ? 'var(--color-down)' : 'var(--text-disabled)',
          opacity: 0.7,
        },
      })),
      barWidth: '60%',
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
  const headers = ['日期', '趋势', '预测区间低', '预测区间高', '当日收盘', '次日实际', '涨跌幅%', '是否命中']
  const rows = store.result.predictions.map(p => {
    const chg = (p.actual_price != null && p.current_price != null)
      ? ((p.actual_price - p.current_price) / p.current_price * 100).toFixed(2)
      : ''
    return [
      p.date, TREND_LABEL_MAP[p.trend] || p.trend, p.predicted_low, p.predicted_high,
      p.current_price ?? '', p.actual_price ?? '', chg,
      p.hit ? '是' : '否',
    ]
  })
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
    <div class="page-header">
      <div class="header-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>回测中心</span>
      </div>
    </div>

    <div class="backtest-layout">
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
                  <el-input-number v-model="form.params!.lookback_days" :step="5" :min="30" :max="252" />
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
          <el-icon><VideoPlay /></el-icon>
          <span>开始回测</span>
        </el-button>
      </div>

      <div class="result-panel">
        <div v-if="store.error" class="error-message">
          <el-icon><Warning /></el-icon>
          <span>{{ store.error }}</span>
        </div>

        <div v-else-if="store.result" class="result-content">
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-label">Day1命中率</span>
              <span class="stat-value font-mono">{{ (store.result.statistics.day1_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day2命中率</span>
              <span class="stat-value font-mono">{{ (store.result.statistics.day2_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day1趋势准确率</span>
              <span class="stat-value font-mono">{{ (store.result.statistics.day1_trend_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">Day2趋势准确率</span>
              <span class="stat-value font-mono">{{ (store.result.statistics.day2_trend_accuracy * 100).toFixed(1) }}%</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">夏普比率</span>
              <span class="stat-value font-mono">{{ store.result.statistics.sharpe_ratio.toFixed(2) }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">最大回撤</span>
              <span class="stat-value loss font-mono">{{ (store.result.statistics.max_drawdown * 100).toFixed(1) }}%</span>
            </div>
          </div>

          <div class="chart-block">
            <div class="chart-header">
              <span class="chart-title">预测区间 vs 实际价格</span>
              <el-button size="small" text class="export-btn" @click="exportCSV">
                <el-icon><Download /></el-icon>
                <span>导出CSV</span>
              </el-button>
            </div>
            <v-chart class="chart chart-lg" :option="priceCompareOption" autoresize />
          </div>

          <div class="chart-block">
            <div class="chart-title">趋势预测准确性</div>
            <v-chart class="chart" :option="trendAccuracyOption" autoresize />
          </div>

          <div class="predictions-table">
            <div class="chart-title">逐日预测明细</div>
            <el-table :data="store.result.predictions.slice((currentPage - 1) * pageSize, currentPage * pageSize)" size="small" class="dark-table">
              <el-table-column prop="date" label="日期" width="110" />
              <el-table-column prop="trend" label="趋势" width="80">
                <template #default="{ row }">
                  <el-tag
                    :type="getTrendTagType(row.trend)"
                    :class="getTrendClass(row.trend)"
                    size="small"
                    effect="dark"
                  >
                    {{ TREND_LABEL_MAP[row.trend] || row.trend }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="预测区间" width="130">
                <template #default="{ row }">
                  {{ (row.predicted_low ?? 0).toFixed(2) }} ~ {{ (row.predicted_high ?? 0).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column label="当日收盘" width="90">
                <template #default="{ row }">
                  {{ row.current_price != null ? row.current_price.toFixed(2) : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="actual_price" label="次日实际" width="90">
                <template #default="{ row }">
                  {{ row.actual_price != null ? row.actual_price.toFixed(2) : '-' }}
                </template>
              </el-table-column>
              <el-table-column label="涨跌幅" width="80">
                <template #default="{ row }">
                  <span v-if="row.actual_price != null && row.current_price != null" :style="{ color: ((row.actual_price - row.current_price) / row.current_price * 100) >= 0 ? 'var(--color-up)' : 'var(--color-down)' }">
                    {{ ((row.actual_price - row.current_price) / row.current_price * 100).toFixed(2) }}%
                  </span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="hit" label="命中" width="70">
                <template #default="{ row }">
                  <el-tag :type="row.hit ? 'success' : 'danger'" size="small" effect="dark">
                    {{ row.hit ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div class="pagination-wrapper" v-if="store.result.predictions.length > pageSize">
              <el-pagination
                v-model:current-page="currentPage"
                :page-size="pageSize"
                :total="store.result.predictions.length"
                layout="prev, pager, next"
                background
                small
              />
            </div>
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

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.header-title .el-icon {
  font-size: 22px;
  color: var(--color-up);
}

.backtest-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 20px;
}

.config-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  height: fit-content;
}

.config-form {
  margin-bottom: 16px;
}

.code-editor :deep(.el-textarea__inner) {
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.6;
  background: var(--bg-secondary);
  border-color: var(--border-default);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
}

.run-btn {
  width: 100%;
  background: linear-gradient(135deg, var(--color-up) 0%, var(--color-accent) 100%) !important;
  border: none !important;
  font-weight: 600;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: var(--transition-base);
}

.run-btn:hover {
  background: linear-gradient(135deg, #4db6ac 0%, #1e88e5 100%) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.3) !important;
  transform: translateY(-1px);
}

.result-panel {
  min-height: 600px;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: var(--color-down-dim);
  border: 1px solid rgba(255, 71, 87, 0.2);
  border-radius: var(--radius-md);
  color: var(--color-down);
}

.result-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: var(--transition-fast);
}

.stat-card:hover {
  border-color: var(--border-active);
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-up);
  letter-spacing: -0.02em;
}

.stat-value.loss {
  color: var(--color-down);
}

.chart-block {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
  transition: var(--transition-fast);
}

.chart-block:hover {
  border-color: var(--border-active);
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  padding-left: 10px;
  border-left: 3px solid var(--color-up);
  letter-spacing: 0.02em;
}

.export-btn {
  color: var(--text-muted) !important;
  font-size: 12px;
}

.export-btn:hover {
  color: var(--color-up) !important;
  background: rgba(0, 212, 170, 0.08) !important;
}

.chart {
  width: 100%;
  height: 280px;
}

.chart-lg {
  height: 360px;
}

.predictions-table {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 16px;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 20px;
  color: var(--text-muted);
  text-align: center;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 20px;
  color: rgba(0, 212, 170, 0.2);
}

.empty-state h3 {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  font-weight: 600;
}

.empty-state p {
  font-size: 13px;
}

.dark-tabs :deep(.el-tabs__item) {
  color: var(--text-muted);
  font-weight: 500;
}

.dark-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-up);
}

.dark-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--color-up);
}

.dark-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-subtle);
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
