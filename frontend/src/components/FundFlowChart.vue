<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import type { FundFlowData } from '@/types'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent])

const props = defineProps<{ data: FundFlowData }>()

const option = ref<any>({})

function buildOption(data: FundFlowData) {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(20, 27, 45, 0.95)',
      borderColor: 'rgba(0, 212, 170, 0.3)',
      textStyle: { color: '#e0e6ed', fontSize: 11 },
    },
    legend: {
      data: ['主力净流入', '散户净流入', '主力净流入占比'],
      textStyle: { color: '#8b92a8', fontSize: 10 },
      top: 4,
      itemGap: 10,
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: { left: 56, right: 20, top: 36, bottom: 20 },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: { color: '#8b92a8', fontSize: 9, showMaxLabel: true },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        axisLine: { show: false },
        axisLabel: { color: '#8b92a8', fontSize: 9, inside: true, margin: 0 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)', type: 'dashed' } },
        axisTick: { show: false },
      },
      {
        type: 'value',
        axisLine: { show: false },
        axisLabel: { color: '#8b92a8', fontSize: 9, inside: true, margin: 0, formatter: '{value}%' },
        splitLine: { show: false },
        axisTick: { show: false },
      },
    ],
    series: [
      {
        name: '主力净流入',
        type: 'bar',
        data: data.main_flow,
        itemStyle: { color: (p: any) => (p.value ?? 0) >= 0 ? '#00d4aa' : '#ff4757', opacity: 0.7 },
      },
      {
        name: '散户净流入',
        type: 'bar',
        data: data.retail_flow,
        itemStyle: { color: (p: any) => (p.value ?? 0) >= 0 ? '#00a8e8' : '#f0a030', opacity: 0.7 },
      },
      {
        name: '主力净流入占比',
        type: 'line',
        yAxisIndex: 1,
        data: data.main_flow_ratio,
        smooth: true,
        lineStyle: { color: '#a855f7', width: 2 },
        symbol: 'none',
      },
    ],
  }
}

watch(() => props.data, (val) => {
  if (val && val.dates.length > 0) {
    option.value = buildOption(val)
  }
}, { immediate: true, deep: true })

onMounted(() => {
  if (props.data && props.data.dates.length > 0) {
    option.value = buildOption(props.data)
  }
})
</script>

<template>
  <div class="fund-flow-chart">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<style scoped>
.fund-flow-chart {
  width: 100%;
  min-height: 240px;
  height: 30vh;
  max-height: 360px;
}

.chart {
  width: 100%;
  height: 100%;
}

@media (max-width: 768px) {
  .fund-flow-chart {
    min-height: 200px;
    height: 25vh;
    max-height: 280px;
  }
}
</style>
