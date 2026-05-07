<script setup lang="ts">
import { ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent,
} from 'echarts/components'
import type { TechnicalChartData } from '@/types'

use([
  CanvasRenderer, BarChart, LineChart,
  GridComponent, TooltipComponent, LegendComponent,
  DataZoomComponent, MarkLineComponent,
])

const props = defineProps<{ data: TechnicalChartData }>()

const macdOption = ref<any>({})
const rsiOption = ref<any>({})
const kdjOption = ref<any>({})

function buildMacdOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    title: {
      text: 'MACD',
      textStyle: { color: '#64748b', fontSize: 11, fontWeight: 600 },
      left: 8,
      top: 4,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: { color: 'rgba(148, 163, 184, 0.2)', type: 'dashed' },
      },
      backgroundColor: 'rgba(10, 14, 26, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.2)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f1f5f9', fontSize: 11, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.4); border-radius: 8px;',
    },
    legend: {
      data: ['MACD', 'DIF', 'DEA'],
      textStyle: { color: '#475569', fontSize: 10 },
      top: 4,
      right: 8,
      itemGap: 12,
      itemWidth: 14,
      itemHeight: 2,
      icon: 'roundRect',
    },
    grid: { left: 48, right: 16, top: 36, bottom: 28, containLabel: false },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
      axisLabel: { color: '#475569', fontSize: 9, showMaxLabel: true },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: {
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 9, inside: true, margin: 0 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)', type: [4, 4] } },
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: 'MACD',
        type: 'bar',
        data: data.macd,
        itemStyle: {
          color: (p: any) => (p.value ?? 0) >= 0 ? 'rgba(0, 212, 170, 0.5)' : 'rgba(255, 71, 87, 0.5)',
          borderRadius: [1, 1, 0, 0],
        },
        barWidth: '50%',
        barMaxWidth: 12,
      },
      {
        name: 'DIF',
        type: 'line',
        data: data.dif,
        smooth: true,
        lineStyle: { color: '#ffa726', width: 1.5 },
        symbol: 'none',
      },
      {
        name: 'DEA',
        type: 'line',
        data: data.dea,
        smooth: true,
        lineStyle: { color: '#42a5f5', width: 1.5 },
        symbol: 'none',
      },
    ],
  }
}

function buildRsiOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    title: {
      text: 'RSI',
      textStyle: { color: '#64748b', fontSize: 11, fontWeight: 600 },
      left: 8,
      top: 4,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10, 14, 26, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.2)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f1f5f9', fontSize: 11, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.4); border-radius: 8px;',
    },
    legend: {
      data: ['RSI(6)', 'RSI(12)'],
      textStyle: { color: '#475569', fontSize: 10 },
      top: 4,
      right: 8,
      itemGap: 12,
      itemWidth: 14,
      itemHeight: 2,
      icon: 'roundRect',
    },
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: false },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
      axisLabel: { color: '#475569', fontSize: 9, showMaxLabel: true },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: {
      min: 0,
      max: 100,
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 9, inside: true, margin: 0 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)', type: [4, 4] } },
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: 'RSI(6)',
        type: 'line',
        data: data.rsi6,
        smooth: true,
        lineStyle: { color: '#26a69a', width: 1.5 },
        symbol: 'none',
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(0, 212, 170, 0.1)' },
              { offset: 1, color: 'rgba(0, 212, 170, 0)' },
            ],
          },
        },
      },
      {
        name: 'RSI(12)',
        type: 'line',
        data: data.rsi12,
        smooth: true,
        lineStyle: { color: '#a855f7', width: 1.5 },
        symbol: 'none',
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(168, 85, 247, 0.1)' },
              { offset: 1, color: 'rgba(168, 85, 247, 0)' },
            ],
          },
        },
      },
      {
        name: '超买线',
        type: 'line',
        data: data.dates.map(() => 70),
        lineStyle: { color: 'rgba(255, 71, 87, 0.3)', width: 1, type: [4, 4] },
        symbol: 'none',
        silent: true,
      },
      {
        name: '超卖线',
        type: 'line',
        data: data.dates.map(() => 30),
        lineStyle: { color: 'rgba(0, 212, 170, 0.3)', width: 1, type: [4, 4] },
        symbol: 'none',
        silent: true,
      },
    ],
  }
}

function buildKdjOption(data: TechnicalChartData) {
  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    title: {
      text: 'KDJ',
      textStyle: { color: '#64748b', fontSize: 11, fontWeight: 600 },
      left: 8,
      top: 4,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10, 14, 26, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.2)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f1f5f9', fontSize: 11, fontFamily: 'SF Mono, JetBrains Mono, monospace' },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.4); border-radius: 8px;',
    },
    legend: {
      data: ['K', 'D', 'J'],
      textStyle: { color: '#475569', fontSize: 10 },
      top: 4,
      right: 8,
      itemGap: 12,
      itemWidth: 14,
      itemHeight: 2,
      icon: 'roundRect',
    },
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: false },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
      axisLabel: { color: '#475569', fontSize: 9, showMaxLabel: true },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: {
      axisLine: { show: false },
      axisLabel: { color: '#475569', fontSize: 9, inside: true, margin: 0 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.02)', type: [4, 4] } },
      axisTick: { show: false },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: 'K',
        type: 'line',
        data: data.k,
        smooth: true,
        lineStyle: { color: '#ffa726', width: 1.5 },
        symbol: 'none',
      },
      {
        name: 'D',
        type: 'line',
        data: data.d,
        smooth: true,
        lineStyle: { color: '#42a5f5', width: 1.5 },
        symbol: 'none',
      },
      {
        name: 'J',
        type: 'line',
        data: data.j,
        smooth: true,
        lineStyle: { color: '#ef5350', width: 1.5 },
        symbol: 'none',
      },
    ],
  }
}

watch(() => props.data, (val) => {
  if (val && val.dates.length > 0) {
    macdOption.value = buildMacdOption(val)
    rsiOption.value = buildRsiOption(val)
    kdjOption.value = buildKdjOption(val)
  }
}, { immediate: true })
</script>

<template>
  <div class="technical-chart">
    <div class="chart-row">
      <div class="chart-cell">
        <v-chart class="chart" :option="macdOption" autoresize />
      </div>
      <div class="chart-cell">
        <v-chart class="chart" :option="rsiOption" autoresize />
      </div>
      <div class="chart-cell">
        <v-chart class="chart" :option="kdjOption" autoresize />
      </div>
    </div>
  </div>
</template>

<style scoped>
.technical-chart {
  width: 100%;
}

.chart-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.chart-cell {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 8px;
  transition: var(--transition-fast);
}

.chart-cell:hover {
  border-color: var(--border-active);
}

.chart {
  width: 100%;
  height: 220px;
}

@media (max-width: 1200px) {
  .chart-row {
    grid-template-columns: 1fr;
  }
  .chart {
    height: 200px;
  }
}

@media (max-width: 768px) {
  .chart {
    height: 180px;
  }
}
</style>
