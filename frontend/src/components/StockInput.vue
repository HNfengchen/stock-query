<script setup lang="ts">
import { ref, watch } from 'vue'
import type { AnalysisRequest } from '@/types'

const props = defineProps<{
  modelValue: AnalysisRequest
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: AnalysisRequest): void
  (e: 'analyze'): void
}>()

const local = ref<AnalysisRequest>({ ...props.modelValue })

watch(() => props.modelValue, (val) => {
  local.value = { ...val }
}, { deep: true })

watch(local, (val) => {
  emit('update:modelValue', val)
}, { deep: true })

function onAnalyze() {
  emit('analyze')
}
</script>

<template>
  <div class="stock-input-panel">
    <div class="input-row">
      <div class="input-group">
        <label>股票代码/名称</label>
        <el-input
          v-model="local.stock_input"
          placeholder="输入股票代码或名称，如 603956"
          size="large"
          class="dark-input"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
      <div class="input-group">
        <label>持仓状态</label>
        <el-select v-model="local.position_status" size="large" class="dark-select">
          <el-option label="未持有" value="未持有" />
          <el-option label="已持有" value="已持有" />
        </el-select>
      </div>
      <div v-if="local.position_status === '已持有'" class="input-group">
        <label>成本价</label>
        <el-input-number
          v-model="local.cost_price"
          :precision="2"
          :step="0.1"
          :min="0"
          size="large"
          class="dark-input-number"
          placeholder="输入成本价"
        />
      </div>
      <div class="input-group btn-group">
        <label>&nbsp;</label>
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          class="analyze-btn"
          @click="onAnalyze"
        >
          <el-icon><TrendCharts /></el-icon>
          开始分析
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stock-input-panel {
  background: linear-gradient(135deg, rgba(0, 212, 170, 0.05) 0%, rgba(0, 168, 232, 0.05) 100%);
  border: 1px solid rgba(0, 212, 170, 0.15);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 24px;
}

.input-row {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-group label {
  font-size: 13px;
  color: #8b92a8;
  font-weight: 500;
}

.input-group:first-child {
  flex: 1;
  min-width: 200px;
}

.btn-group {
  flex-shrink: 0;
}

.analyze-btn {
  background: linear-gradient(135deg, #00d4aa 0%, #00a8e8 100%);
  border: none;
  font-weight: 600;
  padding: 0 32px;
  height: 40px;
}

.analyze-btn:hover {
  background: linear-gradient(135deg, #00e8bc 0%, #00b8f8 100%);
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(0, 212, 170, 0.3);
}

.dark-input :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1);
}

.dark-input :deep(.el-input__inner) {
  color: #e0e6ed;
}

.dark-select :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1);
}

.dark-select :deep(.el-input__inner) {
  color: #e0e6ed;
}

.dark-input-number :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1);
}

.dark-input-number :deep(.el-input__inner) {
  color: #e0e6ed;
}

@media (max-width: 768px) {
  .input-row {
    flex-direction: column;
    align-items: stretch;
  }
  .input-group:first-child {
    min-width: auto;
  }
}
</style>
