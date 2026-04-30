<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import type { TechnicalChartData } from '@/types'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const props = defineProps<{ data: TechnicalChartData }>()

const macdOption = ref<any>({})
const rsiOption = ref<any>({})
const kdjOption = ref<any>({})

const gridBase = { left: 50, right: 12, top: 32, bottom: 20 }
const axisLabelStyle = { color: '#8b92a8', fontSize: 9, inside: true, margin: 0 }
const splitLineStyle = { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } }
const xAxisBase = (data: string[]) => ({
  type: 'category' as const,
  data,
  axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
  axisLabel: { color: '#8b92a8', fontSize: 9, showMaxLabel: true },
  axisTick: { show: false },
})
const tooltipBase = {
  trigger: 'axis' as const,
  backgroundColor: 'rgba(20, 27, 45, 0.95)',
  borderColor: 'rgba(0, 212, 170, 0.3)',
  textStyle: { color: '#e0e6ed', fontSize: 11 },
}
const legendBase = (data: string[]) => ({
  data,
  textStyle: { color: '#8b92a8', fontSize: 10 },
  top: 4,
  itemGap: 8,
  itemWidth: 12,
  itemHeight: 8,
})

function buildMacdOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    tooltip: tooltipBase,
    legend: legendBase(['DIF', 'DEA', 'MACD']),
    grid: gridBase,
    xAxis: xAxisBase(data.dates),
    yAxis: {
      axisLine: { show: false },
      axisLabel: axisLabelStyle,
      splitLine: splitLineStyle,
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 50, end: 100 }],
    series: [
      { name: 'DIF', type: 'line', data: data.dif, smooth: true, lineStyle: { color: '#00a8e8', width: 1.5 }, symbol: 'none' },
      { name: 'DEA', type: 'line', data: data.dea, smooth: true, lineStyle: { color: '#f0a030', width: 1.5 }, symbol: 'none' },
      { name: 'MACD', type: 'bar', data: data.macd, itemStyle: { color: (p: any) => (p.value ?? 0) >= 0 ? '#00d4aa' : '#ff4757', opacity: 0.7 } },
    ],
  }
}

function buildRsiOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    tooltip: tooltipBase,
    legend: legendBase(['RSI(6)', 'RSI(12)']),
    grid: gridBase,
    xAxis: xAxisBase(data.dates),
    yAxis: {
      min: 0, max: 100,
      axisLine: { show: false },
      axisLabel: axisLabelStyle,
      splitLine: splitLineStyle,
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 50, end: 100 }],
    series: [
      { name: 'RSI(6)', type: 'line', data: data.rsi6, smooth: true, lineStyle: { color: '#00d4aa', width: 1.5 }, symbol: 'none' },
      { name: 'RSI(12)', type: 'line', data: data.rsi12, smooth: true, lineStyle: { color: '#a855f7', width: 1.5 }, symbol: 'none' },
    ],
  }
}

function buildKdjOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    tooltip: tooltipBase,
    legend: legendBase(['K', 'D', 'J']),
    grid: gridBase,
    xAxis: xAxisBase(data.dates),
    yAxis: {
      min: 0, max: 100,
      axisLine: { show: false },
      axisLabel: axisLabelStyle,
      splitLine: splitLineStyle,
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 50, end: 100 }],
    series: [
      { name: 'K', type: 'line', data: data.k, smooth: true, lineStyle: { color: '#00d4aa', width: 1.5 }, symbol: 'none' },
      { name: 'D', type: 'line', data: data.d, smooth: true, lineStyle: { color: '#f0a030', width: 1.5 }, symbol: 'none' },
      { name: 'J', type: 'line', data: data.j, smooth: true, lineStyle: { color: '#ff4757', width: 1.5 }, symbol: 'none' },
    ],
  }
}

watch(() => props.data, (val) => {
  if (val && val.dates.length > 0) {
    macdOption.value = buildMacdOption(val)
    rsiOption.value = buildRsiOption(val)
    kdjOption.value = buildKdjOption(val)
  }
}, { immediate: true, deep: true })

onMounted(() => {
  if (props.data && props.data.dates.length > 0) {
    macdOption.value = buildMacdOption(props.data)
    rsiOption.value = buildRsiOption(props.data)
    kdjOption.value = buildKdjOption(props.data)
  }
})
</script>

<template>
  <div class="technical-charts">
    <div class="chart-card">
      <div class="chart-title">MACD</div>
      <v-chart class="chart" :option="macdOption" autoresize />
    </div>
    <div class="chart-card">
      <div class="chart-title">RSI</div>
      <v-chart class="chart" :option="rsiOption" autoresize />
    </div>
    <div class="chart-card">
      <div class="chart-title">KDJ</div>
      <v-chart class="chart" :option="kdjOption" autoresize />
    </div>
  </div>
</template>

<style scoped>
.technical-charts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.chart-card {
  min-width: 0;
}

.chart-title {
  font-size: 12px;
  font-weight: 600;
  color: #e0e6ed;
  margin-bottom: 6px;
  padding-left: 8px;
  border-left: 3px solid #00d4aa;
}

.chart {
  width: 100%;
  height: 200px;
}

@media (max-width: 1200px) {
  .technical-charts {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 768px) {
  .technical-charts {
    grid-template-columns: 1fr;
  }
  .chart {
    height: 180px;
  }
}
</style>
