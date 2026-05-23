<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import type { AnalysisRequest } from '@/types'

const props = defineProps<{
  modelValue: AnalysisRequest
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: AnalysisRequest): void
  (e: 'analyze'): void
  (e: 'cancel'): void
}>()

const local = computed({
  get: () => props.modelValue,
  set: (val: AnalysisRequest) => emit('update:modelValue', val),
})

const debouncePending = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onAnalyze() {
  if (debouncePending.value || props.loading) return
  debouncePending.value = true
  debounceTimer = setTimeout(() => {
    debouncePending.value = false
    debounceTimer = null
    emit('analyze')
  }, 300)
}

function onCancel() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  debouncePending.value = false
  emit('cancel')
}

onUnmounted(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
})
</script>

<template>
  <div class="stock-input-panel">
    <div class="input-row">
      <div class="input-group input-main">
        <label>股票代码 / 名称</label>
        <el-input
          v-model="local.stock_input"
          placeholder="输入股票代码或名称"
          size="large"
          class="dark-input"
          clearable
          @keyup.enter="onAnalyze"
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
      <div v-if="local.position_status === '已持有'" class="input-group input-cost">
        <label>成本价</label>
        <el-input-number
          :model-value="local.cost_price"
          @update:model-value="(v: number | undefined) => local.cost_price = v"
          :precision="2"
          :step="0.1"
          :min="0"
          size="large"
          class="dark-input-number"
          placeholder="0.00"
        />
      </div>
      <div class="input-group btn-group">
        <label>&nbsp;</label>
        <el-button
          v-if="loading"
          type="danger"
          size="large"
          class="cancel-btn"
          @click="onCancel"
        >
          <el-icon><Close /></el-icon>
          <span>取消分析</span>
        </el-button>
        <el-button
          v-else
          type="primary"
          size="large"
          :disabled="debouncePending"
          class="analyze-btn"
          @click="onAnalyze"
        >
          <el-icon><TrendCharts /></el-icon>
          <span>开始分析</span>
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stock-input-panel {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 20px 24px;
  margin-bottom: 20px;
  transition: var(--transition-base, 0.25s ease);
}

.stock-input-panel:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
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
  gap: 6px;
}

.input-group label {
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.input-main {
  flex: 1;
  min-width: 200px;
}

.input-cost {
  width: 150px;
  flex-shrink: 0;
}

.btn-group {
  flex-shrink: 0;
  margin-left: auto;
}

.analyze-btn {
  background: linear-gradient(135deg, var(--color-up) 0%, #00897b 100%) !important;
  border: none !important;
  font-weight: 600;
  font-size: 14px;
  padding: 0 28px;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: var(--transition-base);
}

.analyze-btn:hover {
  background: linear-gradient(135deg, #4db6ac 0%, #26a69a 100%) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.3) !important;
  transform: translateY(-1px);
}

.cancel-btn {
  background: linear-gradient(135deg, #ef5350 0%, #c62828 100%) !important;
  border: none !important;
  font-weight: 600;
  font-size: 14px;
  padding: 0 28px;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: var(--transition-base);
}

.cancel-btn:hover {
  background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%) !important;
  box-shadow: 0 4px 16px rgba(255, 71, 87, 0.3) !important;
  transform: translateY(-1px);
}

.dark-input :deep(.el-input__wrapper) {
  background: var(--bg-secondary, #1a1a1a) !important;
  box-shadow: inset 0 0 0 1px var(--border-default, rgba(255, 255, 255, 0.08)) !important;
  border-radius: var(--radius-sm, 6px) !important;
  padding: 0 12px;
}

.dark-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 1px var(--border-active, rgba(38, 166, 154, 0.4)) !important;
}

.dark-input :deep(.el-input__inner) {
  color: var(--text-primary, rgba(255, 255, 255, 0.92)) !important;
  font-size: 14px;
}

.dark-input :deep(.el-input__prefix) {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.dark-select :deep(.el-input__wrapper) {
  background: var(--bg-secondary, #1a1a1a) !important;
  box-shadow: inset 0 0 0 1px var(--border-default, rgba(255, 255, 255, 0.08)) !important;
  border-radius: var(--radius-sm, 6px) !important;
}

.dark-select :deep(.el-input__inner) {
  color: var(--text-primary, rgba(255, 255, 255, 0.92)) !important;
}

.dark-input-number :deep(.el-input__wrapper) {
  background: var(--bg-secondary, #1a1a1a) !important;
  box-shadow: inset 0 0 0 1px var(--border-default, rgba(255, 255, 255, 0.08)) !important;
  border-radius: var(--radius-sm, 6px) !important;
}

.dark-input-number :deep(.el-input__inner) {
  color: var(--text-primary, rgba(255, 255, 255, 0.92)) !important;
  text-align: left;
  padding-left: 12px;
}

@media (max-width: 768px) {
  .input-row {
    flex-direction: column;
    align-items: stretch;
  }
  .input-main {
    min-width: auto;
  }
  .input-cost {
    width: auto;
  }
}
</style>
