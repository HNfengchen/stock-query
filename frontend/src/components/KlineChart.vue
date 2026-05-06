<script setup lang="ts">
import { ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { CandlestickChart, LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, DataZoomComponent,
  LegendComponent, TitleComponent, MarkLineComponent,
} from 'echarts/components'
import type { KlineData } from '@/types'

use([
  CanvasRenderer, CandlestickChart, LineChart, BarChart,
  GridComponent, TooltipComponent, DataZoomComponent,
  LegendComponent, TitleComponent, MarkLineComponent,
])

const props = defineProps<{ data: KlineData }>()

const option = ref<any>({})

function buildOption(data: KlineData) {
  const upColor = '#00d4aa'
  const downColor = '#ff4757'

  const candleData = data.dates.map((_, i) => [
    data.opens[i] ?? 0,
    data.closes[i] ?? 0,
    data.lows[i] ?? 0,
    data.highs[i] ?? 0,
  ])

  return {
    backgroundColor: 'transparent',
    animation: true,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', lineStyle: { color: '#8b92a8', opacity: 0.5 } },
      backgroundColor: 'rgba(20, 27, 45, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.3)',
      textStyle: { color: '#e0e6ed', fontSize: 12 },
      formatter: (params: any[]) => {
        const date = params[0]?.axisValue || ''
        let html = `<div style="font-weight:600;margin-bottom:6px">${date}</div>`
        params.forEach((p: any) => {
          if (p.seriesName === 'K线') {
            const d = p.data
            html += `<div>开盘: <span style="color:${upColor}">${d[0]}</span> 收盘: <span style="color:${d[1] >= d[0] ? upColor : downColor}">${d[1]}</span></div>`
            html += `<div>最高: <span style="color:${upColor}">${d[3]}</span> 最低: <span style="color:${downColor}">${d[2]}</span></div>`
          } else {
            html += `<div>${p.seriesName}: <span style="color:${p.color}">${p.value}</span></div>`
          }
        })
        return html
      },
    },
    legend: {
      data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60', 'BOLL上轨', 'BOLL中轨', 'BOLL下轨'],
      textStyle: { color: '#8b92a8', fontSize: 11 },
      top: 4,
      itemGap: 10,
      itemWidth: 14,
      itemHeight: 10,
    },
    grid: [
      { left: 60, right: 20, top: 40, bottom: 72 },
      { left: 60, right: 20, top: '76%', bottom: 28 },
    ],
    xAxis: [
      {
        type: 'category',
        data: data.dates,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
        axisLabel: { color: '#8b92a8', fontSize: 10, showMaxLabel: true, showMinLabel: true },
        axisTick: { show: false },
        boundaryGap: false,
      },
      {
        type: 'category',
        gridIndex: 1,
        data: data.dates,
        axisLine: { show: false },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        axisLine: { show: false },
        axisLabel: { color: '#8b92a8', fontSize: 10, inside: false, margin: 8 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } },
        axisTick: { show: false },
      },
      {
        scale: true,
        gridIndex: 1,
        axisLine: { show: false },
        axisLabel: { color: '#8b92a8', fontSize: 9, inside: true, margin: 0 },
        splitLine: { show: false },
        axisTick: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        start: 50,
        end: 100,
        bottom: 4,
        height: 16,
        borderColor: 'transparent',
        fillerColor: 'rgba(0,212,170,0.15)',
        handleStyle: { color: '#00d4aa', borderWidth: 0 },
        textStyle: { color: '#8b92a8', fontSize: 9 },
        showDetail: false,
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candleData,
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
        },
      },
      {
        name: 'MA5',
        type: 'line',
        data: data.ma5,
        smooth: true,
        lineStyle: { color: '#f0a030', width: 1 },
        symbol: 'none',
      },
      {
        name: 'MA10',
        type: 'line',
        data: data.ma10,
        smooth: true,
        lineStyle: { color: '#00a8e8', width: 1 },
        symbol: 'none',
      },
      {
        name: 'MA20',
        type: 'line',
        data: data.ma20,
        smooth: true,
        lineStyle: { color: '#a855f7', width: 1 },
        symbol: 'none',
      },
      {
        name: 'MA60',
        type: 'line',
        data: data.ma60,
        smooth: true,
        lineStyle: { color: '#8b92a8', width: 1 },
        symbol: 'none',
      },
      {
        name: 'BOLL上轨',
        type: 'line',
        data: data.boll_upper,
        smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1, type: 'dashed' },
        symbol: 'none',
      },
      {
        name: 'BOLL中轨',
        type: 'line',
        data: data.boll_middle,
        smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.15)', width: 1, type: 'dashed' },
        symbol: 'none',
      },
      {
        name: 'BOLL下轨',
        type: 'line',
        data: data.boll_lower,
        smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1, type: 'dashed' },
        symbol: 'none',
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: data.volumes,
        itemStyle: {
          color: (p: any) => (data.closes?.[p.dataIndex] ?? 0) >= (data.opens?.[p.dataIndex] ?? 0) ? upColor : downColor,
          opacity: 0.6,
        },
      },
    ],
  }
}

watch(() => props.data, (val) => {
  if (val && val.dates.length > 0) {
    option.value = buildOption(val)
  }
}, { immediate: true })
</script>

<template>
  <div class="kline-chart">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<style scoped>
.kline-chart {
  width: 100%;
  min-height: 420px;
  height: 50vh;
  max-height: 600px;
}

.chart {
  width: 100%;
  height: 100%;
}

@media (max-width: 1200px) {
  .kline-chart {
    min-height: 360px;
    height: 45vh;
  }
}

@media (max-width: 768px) {
  .kline-chart {
    min-height: 300px;
    height: 40vh;
    max-height: 400px;
  }
}
</style>
