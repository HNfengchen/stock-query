<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBacktestStore } from '@/stores/backtestStore'
import { useAsyncState } from '@/composables/useAsyncState'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent } from 'echarts/components'
import type { BacktestRequest, BacktestPrediction, WalkForwardRequest } from '@/types'
import { TREND_LABEL_MAP, getTrendColor, getTrendTagType, getTrendClass } from '@/utils/format'

use([CanvasRenderer, LineChart, BarChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, TitleComponent])

const store = useBacktestStore()
const backtestState = useAsyncState()
const wfState = useAsyncState()

const stockCode = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const activeTab = ref('backtest')

const wfTrainWindow = ref(60)
const wfTestWindow = ref(20)
const wfStep = ref(20)

function fmtPct(val: number | null | undefined, decimals: number = 1): string {
  return val != null ? val.toFixed(decimals) : '-'
}

function buildPriceCompareOption(day: 1 | 2) {
  if (!store.result?.predictions?.length) return {}
  const preds = store.result.predictions
  const dates = preds.map(p => p.date)

  const predHighKey: keyof BacktestPrediction = day === 1 ? 'day1_pred_high' : 'day2_pred_high'
  const predLowKey: keyof BacktestPrediction = day === 1 ? 'day1_pred_low' : 'day2_pred_low'
  const actualKey: keyof BacktestPrediction = day === 1 ? 'actual_day1' : 'actual_day2'
  const hitKey: keyof BacktestPrediction = day === 1 ? 'day1_hit' : 'day2_hit'

  const actualPrices = preds.map(p => p[actualKey] as number | null)

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
        const predHigh = p[predHighKey] as number | null
        const predLow = p[predLowKey] as number | null
        const actual = p[actualKey] as number | null
        const hit = p[hitKey] as boolean | null
        let html = `<div style="font-weight:600;margin-bottom:6px">${p.date}</div>`
        html += `<div>预测趋势: <span style="color:${getTrendColor(p.trend)}">${TREND_LABEL_MAP[p.trend] || p.trend}</span></div>`
        if (predLow != null && predHigh != null) {
          html += `<div>Day${day}预测区间: <span class="font-mono">${predLow.toFixed(2)} ~ ${predHigh.toFixed(2)}</span></div>`
        }
        if (p.current_price != null) {
          html += `<div>当日收盘: <span class="font-mono">${p.current_price.toFixed(2)}</span></div>`
        }
        if (actual != null) {
          html += `<div>Day${day}实际: <span style="color:var(--color-accent, #42a5f5);font-weight:600">${actual.toFixed(2)}</span></div>`
          if (p.current_price != null) {
            const chg = ((actual - p.current_price) / p.current_price * 100).toFixed(2)
            html += `<div>涨跌幅: <span style="color:${parseFloat(chg) >= 0 ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)'}">${chg}%</span></div>`
          }
          if (hit != null) {
            html += `<div>命中: <span style="color:${hit ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)'}">${hit ? '是' : '否'}</span></div>`
          }
        }
        return html
      },
    },
    legend: {
      data: [`Day${day}预测区间`, `Day${day}实际价格`],
      textStyle: { color: 'var(--text-muted, rgba(255, 255, 255, 0.38))', fontSize: 11 },
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
        name: `Day${day}预测区间`,
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
              fill: hit === 1 ? 'rgba(0, 212, 170, 0.2)' : hit === 0 ? 'rgba(255, 71, 87, 0.2)' : 'rgba(100, 116, 139, 0.15)',
              stroke: hit === 1 ? 'var(--color-up, #26a69a)' : hit === 0 ? 'var(--color-down, #ef5350)' : 'var(--text-disabled, rgba(255, 255, 255, 0.22))',
              lineWidth: 1,
            },
          }
        },
        data: preds.map((p, i) => {
          const predLow = p[predLowKey] as number | null
          const predHigh = p[predHighKey] as number | null
          const hit = p[hitKey] as boolean | null
          return [i, predLow, predHigh, hit === true ? 1 : hit === false ? 0 : -1]
        }),
        z: 1,
      },
      {
        name: `Day${day}实际价格`,
        type: 'line',
        data: actualPrices,
        smooth: true,
        lineStyle: { color: 'var(--color-accent, #42a5f5)', width: 2 },
        symbol: 'circle',
        symbolSize: 5,
        itemStyle: { color: 'var(--color-accent, #42a5f5)', borderWidth: 0 },
        z: 2,
      },
    ],
  }
}

const day1PriceOption = computed(() => buildPriceCompareOption(1))
const day2PriceOption = computed(() => buildPriceCompareOption(2))

const trendAccuracyOption = computed(() => {
  if (!store.result?.predictions?.length) return {}
  const preds = store.result.predictions
  const dates = preds.map(p => p.date)

  const day1MatchData: number[] = []
  const day2MatchData: number[] = []

  for (const p of preds) {
    day1MatchData.push(p.day1_trend_correct === true ? 1 : p.day1_trend_correct === false ? 0 : NaN)
    day2MatchData.push(p.day2_trend_correct === true ? 1 : p.day2_trend_correct === false ? 0 : NaN)
  }

  const day1Valid = day1MatchData.filter(v => !isNaN(v))
  const day1Correct = day1Valid.filter(v => v === 1).length
  const day1Pct = day1Valid.length > 0 ? (day1Correct / day1Valid.length * 100).toFixed(1) : '0'

  const day2Valid = day2MatchData.filter(v => !isNaN(v))
  const day2Correct = day2Valid.filter(v => v === 1).length
  const day2Pct = day2Valid.length > 0 ? (day2Correct / day2Valid.length * 100).toFixed(1) : '0'

  return {
    backgroundColor: 'transparent',
    title: {
      text: `趋势准确率  Day1: ${day1Pct}%  Day2: ${day2Pct}%`,
      textStyle: { color: 'var(--text-primary, rgba(255, 255, 255, 0.92))', fontSize: 13, fontWeight: 600 },
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
        if (p.day1_trend_correct != null) {
          html += `<div>Day1趋势: <span style="color:${p.day1_trend_correct ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)'}">${p.day1_trend_correct ? '正确' : '错误'}</span></div>`
        }
        if (p.day2_trend_correct != null) {
          html += `<div>Day2趋势: <span style="color:${p.day2_trend_correct ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)'}">${p.day2_trend_correct ? '正确' : '错误'}</span></div>`
        }
        return html
      },
    },
    legend: {
      data: ['Day1趋势', 'Day2趋势'],
      textStyle: { color: 'var(--text-muted, rgba(255, 255, 255, 0.38))', fontSize: 11 },
      top: 4,
      right: 8,
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
    series: [
      {
        name: 'Day1趋势',
        type: 'bar',
        data: day1MatchData.map((v, i) => ({
          value: isNaN(v) ? null : v,
          itemStyle: {
            color: v === 1 ? 'var(--color-up, #26a69a)' : v === 0 ? 'var(--color-down, #ef5350)' : 'var(--text-disabled, rgba(255, 255, 255, 0.22))',
            opacity: 0.7,
          },
        })),
        barWidth: '30%',
        barGap: '10%',
      },
      {
        name: 'Day2趋势',
        type: 'bar',
        data: day2MatchData.map((v, i) => ({
          value: isNaN(v) ? null : v,
          itemStyle: {
            color: v === 1 ? 'rgba(0, 212, 170, 0.5)' : v === 0 ? 'rgba(255, 71, 87, 0.5)' : 'var(--text-disabled, rgba(255, 255, 255, 0.22))',
            opacity: 0.7,
          },
        })),
        barWidth: '30%',
      },
    ],
  }
})

const wfAccuracyOption = computed(() => {
  if (!store.wfResult?.windows?.length) return {}
  const windows = store.wfResult.windows
  const labels = windows.map(w => `W${w.window_id + 1}`)

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
        const w = windows[idx]
        if (!w) return ''
        let html = `<div style="font-weight:600;margin-bottom:6px">窗口 W${w.window_id + 1}</div>`
        html += `<div>训练期: ${w.train_start} ~ ${w.train_end}</div>`
        html += `<div>测试期: ${w.test_start} ~ ${w.test_end}</div>`
        html += `<div>预测数: ${w.n_predictions}</div>`
        for (const p of params) {
          html += `<div>${p.seriesName}: <span style="font-weight:600">${p.value}%</span></div>`
        }
        return html
      },
    },
    legend: {
      data: ['命中率', '方向准确率', '趋势准确率'],
      textStyle: { color: 'var(--text-muted, rgba(255, 255, 255, 0.38))', fontSize: 11 },
      top: 4,
    },
    grid: { left: 48, right: 16, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: { color: '#475569', fontSize: 10, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 10, formatter: '{value}%', fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)', type: [4, 4] } },
      axisTick: { show: false },
    },
    series: [
      {
        name: '命中率',
        type: 'line',
        data: windows.map(w => w.hit_rate),
        smooth: true,
        lineStyle: { color: 'var(--color-up, #26a69a)', width: 2 },
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: 'var(--color-up, #26a69a)', borderWidth: 0 },
      },
      {
        name: '方向准确率',
        type: 'line',
        data: windows.map(w => w.direction_accuracy),
        smooth: true,
        lineStyle: { color: 'var(--color-accent, #42a5f5)', width: 2 },
        symbol: 'diamond',
        symbolSize: 6,
        itemStyle: { color: 'var(--color-accent, #42a5f5)', borderWidth: 0 },
      },
      {
        name: '趋势准确率',
        type: 'line',
        data: windows.map(w => w.trend_accuracy),
        smooth: true,
        lineStyle: { color: '#f59e0b', width: 2 },
        symbol: 'triangle',
        symbolSize: 6,
        itemStyle: { color: '#f59e0b', borderWidth: 0 },
      },
    ],
  }
})

async function runValidation() {
  if (!stockCode.value.trim() || backtestState.isLoading.value) return
  const data: BacktestRequest = { stock_code: stockCode.value.trim() }
  backtestState.toLoading()
  try {
    await store.executeBacktest(data)
    if (store.result) {
      backtestState.toSuccess(null)
    } else {
      backtestState.toError('验证未返回结果')
    }
  } catch (e: any) {
    backtestState.toError(e.response?.data?.detail || e.message || '预测验证执行失败')
  }
}

async function runWalkForward() {
  if (!stockCode.value.trim() || wfState.isLoading.value) return
  const data: WalkForwardRequest = {
    stock_code: stockCode.value.trim(),
    train_window: wfTrainWindow.value,
    test_window: wfTestWindow.value,
    step: wfStep.value,
  }
  wfState.toLoading()
  try {
    await store.executeWalkForward(data)
    if (store.wfResult) {
      wfState.toSuccess(null)
    } else {
      wfState.toError('Walk-Forward验证未返回结果')
    }
  } catch (e: any) {
    wfState.toError(e.response?.data?.detail || e.message || 'Walk-Forward验证执行失败')
  }
}

function exportCSV() {
  if (!store.result?.predictions?.length) return
  const headers = ['日期', '趋势', 'Day1预测上限', 'Day1预测下限', 'Day2预测上限', 'Day2预测下限', '当日收盘', 'Day1实际', 'Day2实际', 'Day1命中', 'Day2命中', 'Day1趋势正确', 'Day2趋势正确', 'Day1方向正确', 'Day2方向正确']
  const rows = store.result.predictions.map(p => [
    p.date,
    TREND_LABEL_MAP[p.trend] || p.trend,
    p.day1_pred_high ?? '',
    p.day1_pred_low ?? '',
    p.day2_pred_high ?? '',
    p.day2_pred_low ?? '',
    p.current_price ?? '',
    p.actual_day1 ?? '',
    p.actual_day2 ?? '',
    p.day1_hit === true ? '是' : p.day1_hit === false ? '否' : '',
    p.day2_hit === true ? '是' : p.day2_hit === false ? '否' : '',
    p.day1_trend_correct === true ? '是' : p.day1_trend_correct === false ? '否' : '',
    p.day2_trend_correct === true ? '是' : p.day2_trend_correct === false ? '否' : '',
    p.day1_direction_correct === true ? '是' : p.day1_direction_correct === false ? '否' : '',
    p.day2_direction_correct === true ? '是' : p.day2_direction_correct === false ? '否' : '',
  ])
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `prediction_validation_${store.result.stock_code}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="backtest-view">
    <div class="page-header">
      <div class="header-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>预测验证中心</span>
      </div>
    </div>

    <div class="backtest-layout">
      <div class="config-panel">
        <div class="config-form">
          <el-form label-position="top">
            <el-form-item label="股票代码">
              <el-input v-model="stockCode" placeholder="如 603956" @keyup.enter="activeTab === 'backtest' ? runValidation() : runWalkForward()" />
            </el-form-item>
          </el-form>
        </div>

        <el-button v-if="activeTab === 'backtest'" type="primary" class="run-btn" :loading="backtestState.isLoading.value" @click="runValidation">
          <el-icon><VideoPlay /></el-icon>
          <span>开始验证</span>
        </el-button>
        <el-button v-else type="primary" class="run-btn" :loading="wfState.isLoading.value" @click="runWalkForward">
          <el-icon><VideoPlay /></el-icon>
          <span>Walk-Forward验证</span>
        </el-button>

        <div v-if="activeTab === 'walkforward'" class="wf-params">
          <div class="info-item">
            <span class="info-label">训练窗口</span>
            <el-input-number v-model="wfTrainWindow" :min="20" :max="200" :step="10" size="small" controls-position="right" />
          </div>
          <div class="info-item">
            <span class="info-label">测试窗口</span>
            <el-input-number v-model="wfTestWindow" :min="5" :max="60" :step="5" size="small" controls-position="right" />
          </div>
          <div class="info-item">
            <span class="info-label">滑动步长</span>
            <el-input-number v-model="wfStep" :min="5" :max="60" :step="5" size="small" controls-position="right" />
          </div>
        </div>

        <div v-if="store.result && activeTab === 'backtest'" class="info-section">
          <div class="info-item">
            <span class="info-label">股票代码</span>
            <span class="info-value font-mono">{{ store.result.stock_code }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">数据范围</span>
            <span class="info-value font-mono">{{ store.result.data_range }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">预测记录</span>
            <span class="info-value font-mono">{{ store.result.total_predictions }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Day1有效数</span>
            <span class="info-value font-mono">{{ store.result.day1_valid_count }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Day2有效数</span>
            <span class="info-value font-mono">{{ store.result.day2_valid_count }}</span>
          </div>
        </div>

        <div v-if="store.wfResult && activeTab === 'walkforward'" class="info-section">
          <div class="info-item">
            <span class="info-label">股票代码</span>
            <span class="info-value font-mono">{{ store.wfResult.stock_code }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">预测记录</span>
            <span class="info-value font-mono">{{ store.wfResult.total_predictions }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">窗口数量</span>
            <span class="info-value font-mono">{{ store.wfResult.windows.length }}</span>
          </div>
        </div>
      </div>

      <div class="result-panel">
        <el-tabs v-model="activeTab" class="backtest-tabs">
          <el-tab-pane label="预测验证" name="backtest">
            <div v-if="backtestState.isLoading.value" class="loading-state">
              <div class="loading-spinner-wrap">
                <el-icon class="loading-spin"><Loading /></el-icon>
              </div>
              <h3>正在执行预测验证...</h3>
              <p>分析历史预测区间与实际价格的匹配度</p>
            </div>

            <div v-else-if="backtestState.isError.value" class="error-state">
              <el-icon class="error-icon"><WarningFilled /></el-icon>
              <h3>验证执行失败</h3>
              <p>{{ backtestState.error.value }}</p>
              <el-button type="primary" size="small" @click="runValidation">
                <el-icon><RefreshRight /></el-icon>
                <span>重试</span>
              </el-button>
            </div>

            <div v-else-if="backtestState.isSuccess.value && store.result" class="result-content">
              <div class="stats-grid">
                <div class="stat-card">
                  <span class="stat-label">Day1命中率</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day1_hit_rate) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2命中率</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day2_hit_rate) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day1趋势准确率</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day1_trend_accuracy) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2趋势准确率</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day2_trend_accuracy) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day1方向准确率</span>
                  <span class="stat-value font-mono" :class="(store.result.statistics.day1_direction_accuracy ?? 0) >= 50 ? '' : 'loss'">{{ fmtPct(store.result.statistics.day1_direction_accuracy) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2方向准确率</span>
                  <span class="stat-value font-mono" :class="(store.result.statistics.day2_direction_accuracy ?? 0) >= 50 ? '' : 'loss'">{{ fmtPct(store.result.statistics.day2_direction_accuracy) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day1区间宽度</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day1_mean_width_pct != null ? store.result.statistics.day1_mean_width_pct * 100 : null, 2) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2区间宽度</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.result.statistics.day2_mean_width_pct != null ? store.result.statistics.day2_mean_width_pct * 100 : null, 2) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day1中点误差</span>
                  <span class="stat-value loss font-mono">{{ fmtPct(store.result.statistics.day1_midpoint_mae_pct != null ? store.result.statistics.day1_midpoint_mae_pct * 100 : null, 2) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2中点误差</span>
                  <span class="stat-value loss font-mono">{{ fmtPct(store.result.statistics.day2_midpoint_mae_pct != null ? store.result.statistics.day2_midpoint_mae_pct * 100 : null, 2) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day1覆盖宽度比</span>
                  <span class="stat-value font-mono" :class="store.result.statistics.day1_coverage_width_score >= 0 ? '' : 'loss'">{{ fmtPct(store.result.statistics.day1_coverage_width_score != null ? store.result.statistics.day1_coverage_width_score * 100 : null, 2) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Day2覆盖宽度比</span>
                  <span class="stat-value font-mono" :class="store.result.statistics.day2_coverage_width_score >= 0 ? '' : 'loss'">{{ fmtPct(store.result.statistics.day2_coverage_width_score != null ? store.result.statistics.day2_coverage_width_score * 100 : null, 2) }}%</span>
                </div>
              </div>

              <div class="chart-block">
                <div class="chart-header">
                  <span class="chart-title">Day1 预测区间 vs 实际价格</span>
                </div>
                <v-chart class="chart chart-lg" :option="day1PriceOption" autoresize />
              </div>

              <div class="chart-block">
                <div class="chart-header">
                  <span class="chart-title">Day2 预测区间 vs 实际价格</span>
                </div>
                <v-chart class="chart chart-lg" :option="day2PriceOption" autoresize />
              </div>

              <div class="chart-block">
                <div class="chart-title">趋势预测准确性</div>
                <v-chart class="chart" :option="trendAccuracyOption" autoresize />
              </div>

              <div class="predictions-table">
                <div class="chart-header">
                  <span class="chart-title">逐日预测明细</span>
                  <el-button size="small" text class="export-btn" @click="exportCSV">
                    <el-icon><Download /></el-icon>
                    <span>导出CSV</span>
                  </el-button>
                </div>
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
                  <el-table-column label="Day1预测区间" width="130">
                    <template #default="{ row }">
                      {{ row.day1_pred_low != null ? row.day1_pred_low.toFixed(2) : '-' }} ~ {{ row.day1_pred_high != null ? row.day1_pred_high.toFixed(2) : '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Day2预测区间" width="130">
                    <template #default="{ row }">
                      {{ row.day2_pred_low != null ? row.day2_pred_low.toFixed(2) : '-' }} ~ {{ row.day2_pred_high != null ? row.day2_pred_high.toFixed(2) : '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="当日收盘" width="90">
                    <template #default="{ row }">
                      {{ row.current_price != null ? row.current_price.toFixed(2) : '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Day1实际" width="90">
                    <template #default="{ row }">
                      {{ row.actual_day1 != null ? row.actual_day1.toFixed(2) : '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Day2实际" width="90">
                    <template #default="{ row }">
                      {{ row.actual_day2 != null ? row.actual_day2.toFixed(2) : '-' }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Day1命中" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day1_hit != null" :type="row.day1_hit ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day1_hit ? '是' : '否' }}
                      </el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Day2命中" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day2_hit != null" :type="row.day2_hit ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day2_hit ? '是' : '否' }}
                      </el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Day1趋势" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day1_trend_correct != null" :type="row.day1_trend_correct ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day1_trend_correct ? '对' : '错' }}
                      </el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Day2趋势" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day2_trend_correct != null" :type="row.day2_trend_correct ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day2_trend_correct ? '对' : '错' }}
                      </el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Day1方向" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day1_direction_correct != null" :type="row.day1_direction_correct ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day1_direction_correct ? '对' : '错' }}
                      </el-tag>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="Day2方向" width="80">
                    <template #default="{ row }">
                      <el-tag v-if="row.day2_direction_correct != null" :type="row.day2_direction_correct ? 'success' : 'danger'" size="small" effect="dark">
                        {{ row.day2_direction_correct ? '对' : '错' }}
                      </el-tag>
                      <span v-else>-</span>
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
              <h3>输入股票代码开始预测验证</h3>
              <p>验证历史预测区间与实际价格的匹配度，评估预测可靠性</p>
            </div>
          </el-tab-pane>

          <el-tab-pane label="Walk-Forward" name="walkforward">
            <div v-if="wfState.isLoading.value" class="loading-state">
              <div class="loading-spinner-wrap">
                <el-icon class="loading-spin"><Loading /></el-icon>
              </div>
              <h3>正在执行 Walk-Forward 验证...</h3>
              <p>通过滚动窗口验证预测模型的稳定性</p>
            </div>

            <div v-else-if="wfState.isError.value" class="error-state">
              <el-icon class="error-icon"><WarningFilled /></el-icon>
              <h3>Walk-Forward 验证失败</h3>
              <p>{{ wfState.error.value }}</p>
              <el-button type="primary" size="small" @click="runWalkForward">
                <el-icon><RefreshRight /></el-icon>
                <span>重试</span>
              </el-button>
            </div>

            <div v-else-if="wfState.isSuccess.value && store.wfResult" class="result-content">
              <div class="stats-grid">
                <div class="stat-card">
                  <span class="stat-label">平均命中率</span>
                  <span class="stat-value font-mono">{{ fmtPct(store.wfResult.overall.avg_hit_rate) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">平均方向准确率</span>
                  <span class="stat-value font-mono" :class="store.wfResult.overall.avg_direction_accuracy >= 50 ? '' : 'loss'">{{ fmtPct(store.wfResult.overall.avg_direction_accuracy) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">平均趋势准确率</span>
                  <span class="stat-value font-mono" :class="store.wfResult.overall.avg_trend_accuracy >= 50 ? '' : 'loss'">{{ fmtPct(store.wfResult.overall.avg_trend_accuracy) }}%</span>
                </div>
              </div>

              <div class="chart-block">
                <div class="chart-header">
                  <span class="chart-title">逐窗口准确率</span>
                </div>
                <v-chart class="chart chart-lg" :option="wfAccuracyOption" autoresize />
              </div>

              <div class="chart-block">
                <div class="chart-header">
                  <span class="chart-title">稳定性指标</span>
                </div>
                <div class="stability-grid">
                  <div class="stability-card">
                    <span class="stability-label">命中率标准差</span>
                    <span class="stability-value font-mono" :class="store.wfResult.stability.hit_rate_std <= 15 ? '' : 'loss'">{{ fmtPct(store.wfResult.stability.hit_rate_std, 2) }}%</span>
                    <span class="stability-hint">越小越稳定</span>
                  </div>
                  <div class="stability-card">
                    <span class="stability-label">方向准确率标准差</span>
                    <span class="stability-value font-mono" :class="store.wfResult.stability.direction_accuracy_std <= 15 ? '' : 'loss'">{{ fmtPct(store.wfResult.stability.direction_accuracy_std, 2) }}%</span>
                    <span class="stability-hint">越小越稳定</span>
                  </div>
                  <div class="stability-card">
                    <span class="stability-label">趋势准确率标准差</span>
                    <span class="stability-value font-mono" :class="store.wfResult.stability.trend_accuracy_std <= 15 ? '' : 'loss'">{{ fmtPct(store.wfResult.stability.trend_accuracy_std, 2) }}%</span>
                    <span class="stability-hint">越小越稳定</span>
                  </div>
                  <div class="stability-card">
                    <span class="stability-label">Sharpe比率</span>
                    <span class="stability-value font-mono" :class="store.wfResult.stability.sharpe_ratio >= 1 ? '' : 'loss'">{{ fmtPct(store.wfResult.stability.sharpe_ratio, 3) }}</span>
                    <span class="stability-hint">命中率均值/标准差</span>
                  </div>
                </div>
              </div>

              <div class="predictions-table">
                <div class="chart-header">
                  <span class="chart-title">窗口明细</span>
                </div>
                <el-table :data="store.wfResult.windows" size="small" class="dark-table">
                  <el-table-column prop="window_id" label="窗口" width="70">
                    <template #default="{ row }">
                      W{{ row.window_id + 1 }}
                    </template>
                  </el-table-column>
                  <el-table-column label="训练期" width="200">
                    <template #default="{ row }">
                      {{ row.train_start }} ~ {{ row.train_end }}
                    </template>
                  </el-table-column>
                  <el-table-column label="测试期" width="200">
                    <template #default="{ row }">
                      {{ row.test_start }} ~ {{ row.test_end }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="n_predictions" label="预测数" width="80" />
                  <el-table-column prop="hit_rate" label="命中率" width="90">
                    <template #default="{ row }">
                      <span class="font-mono" :style="{ color: row.hit_rate >= 50 ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)' }">{{ fmtPct(row.hit_rate) }}%</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="direction_accuracy" label="方向准确率" width="100">
                    <template #default="{ row }">
                      <span class="font-mono" :style="{ color: row.direction_accuracy >= 50 ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)' }">{{ fmtPct(row.direction_accuracy) }}%</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="trend_accuracy" label="趋势准确率" width="100">
                    <template #default="{ row }">
                      <span class="font-mono" :style="{ color: row.trend_accuracy >= 50 ? 'var(--color-up, #26a69a)' : 'var(--color-down, #ef5350)' }">{{ fmtPct(row.trend_accuracy) }}%</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>

            <div v-else class="empty-state">
              <el-icon class="empty-icon"><DataAnalysis /></el-icon>
              <h3>输入股票代码开始 Walk-Forward 验证</h3>
              <p>通过滚动窗口验证预测模型的稳定性，评估不同时间段的表现一致性</p>
            </div>
          </el-tab-pane>
        </el-tabs>
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
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.header-title .el-icon {
  font-size: 22px;
  color: var(--color-up, #26a69a);
}

.backtest-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
}

.config-panel {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 20px;
  height: fit-content;
}

.config-form {
  margin-bottom: 16px;
}

.run-btn {
  width: 100%;
  background: linear-gradient(135deg, var(--color-up, #26a69a) 0%, var(--color-accent, #42a5f5) 100%) !important;
  border: none !important;
  font-weight: 600;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: var(--transition-base, 0.25s ease);
}

.run-btn:hover {
  background: linear-gradient(135deg, #4db6ac 0%, #1e88e5 100%) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.3) !important;
  transform: translateY(-1px);
}

.wf-params {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wf-params .info-item {
  align-items: center;
}

.info-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-label {
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.info-value {
  font-size: 13px;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  font-weight: 500;
}

.result-panel {
  min-height: 600px;
  overflow-x: hidden;
}

.backtest-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.backtest-tabs :deep(.el-tabs__item) {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.backtest-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-up, #26a69a);
}

.backtest-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--color-up, #26a69a);
}

.error-message {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: var(--color-down-dim, rgba(239, 83, 80, 0.15));
  border: 1px solid rgba(255, 71, 87, 0.2);
  border-radius: var(--radius-md, 10px);
  color: var(--color-down, #ef5350);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 20px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  text-align: center;
}

.loading-spinner-wrap {
  margin-bottom: 20px;
}

.loading-spin {
  font-size: 40px;
  color: var(--color-up, #26a69a);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-state h3 {
  font-size: 18px;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  margin-bottom: 8px;
  font-weight: 600;
}

.loading-state p {
  font-size: 13px;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
  gap: 12px;
}

.error-state .error-icon {
  font-size: 48px;
  color: var(--color-down, #ef5350);
}

.error-state h3 {
  font-size: 18px;
  color: var(--color-down, #ef5350);
  font-weight: 600;
}

.error-state p {
  font-size: 13px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  max-width: 400px;
}

.result-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-x: auto;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  overflow-x: auto;
}

.stat-card {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: var(--transition-fast, 0.15s ease);
}

.stat-card:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-up, #26a69a);
  letter-spacing: -0.02em;
}

.stat-value.loss {
  color: var(--color-down, #ef5350);
}

.chart-block {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  transition: var(--transition-fast, 0.15s ease);
}

.chart-block:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  padding-left: 10px;
  border-left: 3px solid var(--color-up, #26a69a);
  letter-spacing: 0.02em;
}

.export-btn {
  color: var(--text-muted, rgba(255, 255, 255, 0.38)) !important;
  font-size: 12px;
}

.export-btn:hover {
  color: var(--color-up, #26a69a) !important;
  background: rgba(0, 212, 170, 0.08) !important;
}

.chart {
  width: 100%;
  height: 280px;
  max-height: 45vh;
}

.chart-lg {
  height: 360px;
  max-height: 55vh;
}

@media (max-height: 900px) {
  .chart { height: 220px; max-height: 35vh; }
  .chart-lg { height: 280px; max-height: 45vh; }
}

@media (max-height: 700px) {
  .chart { height: 180px; max-height: 30vh; }
  .chart-lg { height: 220px; max-height: 38vh; }
}

.stability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  padding-top: 8px;
}

.stability-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: rgba(0, 212, 170, 0.04);
  border: 1px solid rgba(0, 212, 170, 0.1);
  border-radius: var(--radius-md, 10px);
}

.stability-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.stability-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-up, #26a69a);
}

.stability-value.loss {
  color: var(--color-down, #ef5350);
}

.stability-hint {
  font-size: 10px;
  color: var(--text-disabled, rgba(255, 255, 255, 0.22));
}

.predictions-table {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  overflow-x: auto;
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
  .backtest-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .predictions-table :deep(.el-table) {
    font-size: 11px;
  }
}
</style>
