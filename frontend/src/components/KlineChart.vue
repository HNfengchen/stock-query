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

function buildOption(raw: KlineData) {
  const upColor = '#26a69a'
  const downColor = '#ef5350'

  const candleData = raw.dates.map((_, i) => [
    raw.opens[i] ?? 0,
    raw.closes[i] ?? 0,
    raw.lows[i] ?? 0,
    raw.highs[i] ?? 0,
  ])

  const volColors = raw.volumes.map((_, i) => {
    const close = raw.closes[i] ?? 0
    const prevClose = i > 0 ? (raw.closes[i - 1] ?? close) : close
    const isUp = close >= prevClose
    return {
      value: raw.volumes[i],
      itemStyle: {
        color: isUp ? upColor : downColor,
        opacity: 0.5,
        borderRadius: [2, 2, 0, 0],
      },
    }
  })

  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: { color: 'rgba(148, 163, 184, 0.3)', type: 'dashed' },
        label: { backgroundColor: 'rgba(20, 27, 45, 0.95)', color: '#e2e8f0', fontSize: 10, fontFamily: 'monospace' },
      },
      backgroundColor: 'rgba(20, 27, 45, 0.98)',
      borderColor: 'rgba(38, 166, 154, 0.3)',
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: '#e2e8f0', fontSize: 12, fontFamily: 'monospace' },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.5); border-radius: 8px;',
      formatter: (params: any[]) => {
        const idx = params[0]?.dataIndex
        if (idx === undefined || idx < 0) return ''
        const date = raw.dates[idx]
        const o = raw.opens[idx] ?? 0
        const c = raw.closes[idx] ?? 0
        const h = raw.highs[idx] ?? 0
        const l = raw.lows[idx] ?? 0
        const v = raw.volumes[idx] ?? 0
        const isUp = c >= o
        const color = isUp ? upColor : downColor

        let html = `<div style="font-weight:700;margin-bottom:8px;font-size:13px;color:#e2e8f0">${date}</div>`
        html += `<div style="display:grid;grid-template-columns:auto auto;gap:4px 16px">`
        html += `<span style="color:#8b92a8">开盘</span><span style="color:${color};font-weight:600">${o.toFixed(2)}</span>`
        html += `<span style="color:#8b92a8">收盘</span><span style="color:${color};font-weight:600">${c.toFixed(2)}</span>`
        html += `<span style="color:#8b92a8">最高</span><span style="color:${upColor};font-weight:600">${h.toFixed(2)}</span>`
        html += `<span style="color:#8b92a8">最低</span><span style="color:${downColor};font-weight:600">${l.toFixed(2)}</span>`
        html += `<span style="color:#8b92a8">成交量</span><span style="color:#8b92a8;font-weight:600">${(v / 10000).toFixed(1)}万</span>`
        params.forEach((p: any) => {
          if (p.seriesName !== 'K线' && p.seriesName !== '成交量' && p.value != null) {
            html += `<span style="color:#8b92a8">${p.seriesName}</span><span style="color:${p.color};font-weight:600">${p.value.toFixed(2)}</span>`
          }
        })
        html += `</div>`
        return html
      },
    },
    legend: {
      data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60', 'BOLL上轨', 'BOLL中轨', 'BOLL下轨'],
      textStyle: { color: '#64748b', fontSize: 10, fontFamily: 'monospace' },
      top: 4,
      itemGap: 12,
      itemWidth: 16,
      itemHeight: 2,
      icon: 'roundRect',
    },
    grid: [
      { left: 56, right: 16, top: 44, bottom: 80, containLabel: false },
      { left: 56, right: 16, top: '78%', bottom: 32, containLabel: false },
    ],
    xAxis: [
      {
        type: 'category',
        data: raw.dates,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
        axisLabel: { color: '#64748b', fontSize: 10, fontFamily: 'monospace', showMaxLabel: true, showMinLabel: true, formatter: (value: string) => value.slice(5) },
        axisTick: { show: false },
        boundaryGap: true,
        splitLine: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: raw.dates,
        axisLine: { show: false },
        axisLabel: { show: false },
        axisTick: { show: false },
        boundaryGap: true,
      },
    ],
    yAxis: [
      {
        scale: true,
        axisLine: { show: false },
        axisLabel: { color: '#64748b', fontSize: 10, fontFamily: 'monospace', inside: false, margin: 8, formatter: (value: number) => value.toFixed(2) },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: [4, 4] } },
        axisTick: { show: false },
      },
      {
        scale: true,
        gridIndex: 1,
        axisLine: { show: false },
        axisLabel: { color: '#64748b', fontSize: 9, fontFamily: 'monospace', inside: true, margin: 0, formatter: (value: number) => { if (value >= 100000000) return (value / 100000000).toFixed(1) + '亿'; if (value >= 10000) return (value / 10000).toFixed(0) + '万'; return value.toString() } },
        splitLine: { show: false },
        axisTick: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: Math.max(0, raw.dates.length - 60), end: 100, zoomOnMouseWheel: true, moveOnMouseMove: true },
      {
        type: 'slider', xAxisIndex: [0, 1], start: Math.max(0, raw.dates.length - 60), end: 100,
        bottom: 4, height: 18, borderColor: 'transparent',
        backgroundColor: 'rgba(255,255,255,0.02)',
        fillerColor: 'rgba(38, 166, 154, 0.12)',
        handleStyle: { color: '#26a69a', borderColor: '#26a69a', borderWidth: 1, shadowBlur: 4, shadowColor: 'rgba(38, 166, 154, 0.3)' },
        textStyle: { color: '#64748b', fontSize: 9 },
        showDetail: false, brushSelect: false,
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
          borderWidth: 1,
        },
        emphasis: { itemStyle: { borderWidth: 2, shadowBlur: 8, shadowColor: 'rgba(38, 166, 154, 0.3)' } },
      },
      {
        name: 'MA5', type: 'line', data: raw.ma5, smooth: false,
        lineStyle: { color: '#f0b429', width: 1.2, opacity: 0.9 }, symbol: 'none', silent: true,
      },
      {
        name: 'MA10', type: 'line', data: raw.ma10, smooth: false,
        lineStyle: { color: '#4fc3f7', width: 1.2, opacity: 0.9 }, symbol: 'none', silent: true,
      },
      {
        name: 'MA20', type: 'line', data: raw.ma20, smooth: false,
        lineStyle: { color: '#ab47bc', width: 1.2, opacity: 0.9 }, symbol: 'none', silent: true,
      },
      {
        name: 'MA60', type: 'line', data: raw.ma60, smooth: false,
        lineStyle: { color: '#78909c', width: 1, opacity: 0.7 }, symbol: 'none', silent: true,
      },
      {
        name: 'BOLL上轨', type: 'line', data: raw.boll_upper, smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.15)', width: 1, type: [4, 4] }, symbol: 'none', silent: true,
      },
      {
        name: 'BOLL中轨', type: 'line', data: raw.boll_middle, smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.08)', width: 1, type: [4, 4] }, symbol: 'none', silent: true,
      },
      {
        name: 'BOLL下轨', type: 'line', data: raw.boll_lower, smooth: true,
        lineStyle: { color: 'rgba(255,255,255,0.15)', width: 1, type: [4, 4] }, symbol: 'none', silent: true,
      },
      {
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
        data: volColors, barWidth: '55%', barMaxWidth: 20, barMinWidth: 2,
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
  min-height: 440px;
  height: 52vh;
  max-height: 640px;
}

.chart {
  width: 100%;
  height: 100%;
}

@media (max-width: 1200px) {
  .kline-chart { min-height: 380px; height: 48vh; }
}

@media (max-width: 768px) {
  .kline-chart { min-height: 320px; height: 42vh; max-height: 420px; }
}
</style>
