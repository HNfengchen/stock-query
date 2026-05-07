<script setup lang="ts">
import { ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import type { FundFlowData } from '@/types'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const props = defineProps<{ data: FundFlowData }>()

const option = ref<any>({})

function formatAmount(value: number): string {
  if (Math.abs(value) >= 100000000) return (value / 100000000).toFixed(2) + '亿'
  if (Math.abs(value) >= 10000) return (value / 10000).toFixed(1) + '万'
  return value.toFixed(0)
}

function buildOption(data: FundFlowData) {
  const upColor = '#26a69a'
  const downColor = '#ef5350'

  const mainFlowData = data.main_flow.map((v: number) => ({
    value: v,
    itemStyle: {
      color: v >= 0 ? upColor : downColor,
      opacity: 0.85,
      borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
    },
  }))

  const smallFlowData = data.small_flow.map((v: number) => ({
    value: v,
    itemStyle: {
      color: v >= 0 ? '#42a5f5' : '#ffa726',
      opacity: 0.7,
      borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
    },
  }))

  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 400,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(38, 166, 154, 0.05)' } },
      backgroundColor: 'rgba(20, 27, 45, 0.98)',
      borderColor: 'rgba(38, 166, 154, 0.3)',
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: '#e2e8f0', fontSize: 11, fontFamily: 'monospace' },
      extraCssText: 'box-shadow: 0 8px 32px rgba(0,0,0,0.5); border-radius: 8px;',
      formatter: (params: any[]) => {
        if (!params || params.length === 0) return ''
        const date = params[0]?.axisValue || ''
        let html = `<div style="font-weight:700;margin-bottom:8px;font-size:12px;color:#e2e8f0">${date}</div>`
        html += `<div style="display:grid;grid-template-columns:auto auto;gap:4px 16px">`
        params.forEach((p: any) => {
          if (p.value == null) return
          const val = typeof p.value === 'object' ? p.value.value : p.value
          const label = p.seriesName
          if (label === '主力净流入' || label === '小单净流入') {
            html += `<span style="color:rgba(255,255,255,0.6)">${label}</span><span style="color:${p.color};font-weight:600">${formatAmount(val)}</span>`
          } else if (label === '主力占比') {
            html += `<span style="color:rgba(255,255,255,0.6)">${label}</span><span style="color:${p.color};font-weight:600">${val.toFixed(2)}%</span>`
          } else if (label === '涨跌幅') {
            const color = val >= 0 ? upColor : downColor
            html += `<span style="color:rgba(255,255,255,0.6)">${label}</span><span style="color:${color};font-weight:600">${val >= 0 ? '+' : ''}${val.toFixed(2)}%</span>`
          }
        })
        html += `</div>`
        return html
      },
    },
    legend: {
      data: ['主力净流入', '小单净流入', '主力占比', '涨跌幅'],
      textStyle: { color: 'rgba(255,255,255,0.38)', fontSize: 10 },
      top: 4,
      right: 8,
      itemGap: 10,
      itemWidth: 14,
      itemHeight: 2,
      icon: 'roundRect',
    },
    grid: { left: 64, right: 56, top: 40, bottom: 36, containLabel: false },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisLabel: {
        color: 'rgba(255,255,255,0.38)',
        fontSize: 9,
        showMaxLabel: true,
        interval: 'auto',
        formatter: (value: string) => value.slice(5),
      },
      axisTick: { show: false },
      boundaryGap: true,
    },
    yAxis: [
      {
        type: 'value',
        name: '',
        axisLine: { show: false },
        axisLabel: {
          color: 'rgba(255,255,255,0.38)',
          fontSize: 9,
          inside: false,
          margin: 8,
          formatter: (value: number) => formatAmount(value),
        },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: [4, 4] } },
        axisTick: { show: false },
      },
      {
        type: 'value',
        name: '',
        axisLine: { show: false },
        axisLabel: {
          color: 'rgba(255,255,255,0.38)',
          fontSize: 9,
          inside: false,
          margin: 8,
          formatter: '{value}%',
        },
        splitLine: { show: false },
        axisTick: { show: false },
      },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: 0, start: 0, end: 100 }],
    series: [
      {
        name: '主力净流入',
        type: 'bar',
        data: mainFlowData,
        barWidth: '30%',
        barMaxWidth: 18,
        barGap: '30%',
      },
      {
        name: '小单净流入',
        type: 'bar',
        data: smallFlowData,
        barWidth: '30%',
        barMaxWidth: 18,
        barGap: '30%',
      },
      {
        name: '主力占比',
        type: 'line',
        yAxisIndex: 1,
        data: data.main_flow_ratio,
        smooth: true,
        lineStyle: { color: '#ab47bc', width: 2 },
        symbol: 'circle',
        symbolSize: 4,
        itemStyle: { color: '#ab47bc', borderWidth: 0 },
        emphasis: {
          itemStyle: { borderWidth: 2, borderColor: '#ab47bc', shadowBlur: 6, shadowColor: 'rgba(171, 71, 188, 0.4)' },
        },
      },
      {
        name: '涨跌幅',
        type: 'line',
        yAxisIndex: 1,
        data: data.change_pct,
        smooth: true,
        lineStyle: { color: '#ffd54f', width: 1.5, type: 'dashed' },
        symbol: 'diamond',
        symbolSize: 4,
        itemStyle: { color: '#ffd54f', borderWidth: 0 },
        emphasis: {
          itemStyle: { borderWidth: 2, borderColor: '#ffd54f', shadowBlur: 6, shadowColor: 'rgba(255, 213, 79, 0.4)' },
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
  <div class="fund-flow-chart">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<style scoped>
.fund-flow-chart {
  width: 100%;
  min-height: 300px;
  height: 36vh;
  max-height: 440px;
}

.chart {
  width: 100%;
  height: 100%;
}

@media (max-width: 768px) {
  .fund-flow-chart {
    min-height: 240px;
    height: 30vh;
    max-height: 340px;
  }
}
</style>
