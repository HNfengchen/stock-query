<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { useStockStore } from '@/stores/stockStore'
import { useAsyncState } from '@/composables/useAsyncState'
import { useRouter } from 'vue-router'
import type { AnalysisRequest, WatchlistItem } from '@/types'
import { DataAnalysis } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const store = useStockStore()
const router = useRouter()
const batchState = useAsyncState()

const dialogVisible = ref(false)
const editDialogVisible = ref(false)
const editingStock = ref<WatchlistItem | null>(null)
const batchStartTime = ref<number | null>(null)
const tickCounter = ref(0)
const batchDebouncePending = ref(false)
let tickTimer: ReturnType<typeof setInterval> | null = null
let batchDebounceTimer: ReturnType<typeof setTimeout> | null = null

function startTick() {
  stopTick()
  tickTimer = setInterval(() => { tickCounter.value++ }, 1000)
}

function stopTick() {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

onUnmounted(() => { stopTick() })

const newStock = ref<AnalysisRequest>({
  stock_input: '',
  position_status: '未持有',
  cost_price: undefined,
})

const isBatchAnalyzing = computed(() => store.loading && store.batchProgress.status === 'analyzing')

const batchElapsed = computed(() => {
  tickCounter.value
  if (!batchStartTime.value || !isBatchAnalyzing.value) return ''
  const sec = Math.round((Date.now() - batchStartTime.value) / 1000)
  if (sec < 60) return `${sec}秒`
  return `${Math.floor(sec / 60)}分${sec % 60}秒`
})

const batchEta = computed(() => {
  tickCounter.value
  if (!batchStartTime.value || !isBatchAnalyzing.value || store.batchProgress.current === 0) return ''
  const elapsed = (Date.now() - batchStartTime.value) / 1000
  const perItem = elapsed / store.batchProgress.current
  const remaining = Math.round(perItem * (store.batchProgress.total - store.batchProgress.current))
  if (remaining < 0) return ''
  if (remaining < 60) return `约${remaining}秒`
  return `约${Math.floor(remaining / 60)}分${remaining % 60}秒`
})

const batchPercentage = computed(() => {
  if (store.batchProgress.total === 0) return 0
  return Math.round((store.batchProgress.current / store.batchProgress.total) * 100)
})

onMounted(() => {
  store.loadWatchlist()
})

function openAddDialog() {
  newStock.value = { stock_input: '', position_status: '未持有', cost_price: undefined }
  dialogVisible.value = true
}

async function confirmAdd() {
  if (!newStock.value.stock_input.trim()) return
  try {
    await store.addStock(newStock.value)
    dialogVisible.value = false
  } catch (e) {
    console.error(e)
  }
}

function analyzeStock(item: WatchlistItem) {
  const query: Record<string, string> = { code: item.stock_code }
  if (item.position_status) query.position = item.position_status
  if (item.cost_price) query.cost = String(item.cost_price)
  router.push({ path: '/', query })
}

function openEdit(item: WatchlistItem) {
  editingStock.value = { ...item }
  editDialogVisible.value = true
}

function onEditPositionChange() {
  if (editingStock.value?.position_status === '未持有') {
    editingStock.value.cost_price = null
  }
}

function getSignalClass(signal: string): string {
  if (!signal) return ''
  if (['建议买入', '强烈买入', '强烈加仓', '买入', '加仓', '可考虑买入', '继续持有'].includes(signal)) return 'signal-bull'
  if (['减仓', '卖出', '回避', '谨慎持有', '不建议买入'].includes(signal)) return 'signal-bear'
  return 'signal-info'
}

async function batchQuickAnalyze() {
  if (store.watchlist.length === 0 || batchDebouncePending.value || batchState.isLoading.value) return
  batchDebouncePending.value = true
  batchDebounceTimer = setTimeout(async () => {
    batchDebouncePending.value = false
    batchDebounceTimer = null
    const stocks: AnalysisRequest[] = store.watchlist.map(item => ({
      stock_input: item.stock_code,
      position_status: item.position_status,
      cost_price: item.cost_price ?? undefined,
    }))
    batchStartTime.value = Date.now()
    startTick()
    batchState.toLoading()
    try {
      await store.runBatchQuickAnalysis(stocks)
      if (store.batchError) {
        batchState.toError(store.batchError)
        ElMessage.warning(store.batchError)
      } else if (store.batchProgress.status === 'completed') {
        batchState.toSuccess(null)
        ElMessage.success(`分析完成: ${store.batchProgress.total}只股票`)
      }
    } catch (e: any) {
      const message = e.message || '分析失败'
      batchState.toError(message)
      ElMessage.error(message)
    } finally {
      batchStartTime.value = null
      stopTick()
    }
  }, 300)
}

function cancelBatch() {
  if (batchDebounceTimer) {
    clearTimeout(batchDebounceTimer)
    batchDebounceTimer = null
    batchDebouncePending.value = false
  }
  store.cancelBatchAnalysis()
  batchStartTime.value = null
  stopTick()
  batchState.reset()
  ElMessage.info('已取消分析')
}

async function confirmEdit() {
  if (!editingStock.value) return
  try {
    await store.updateStock(editingStock.value.stock_code, {
      position_status: editingStock.value.position_status,
      cost_price: editingStock.value.cost_price,
    })
    editDialogVisible.value = false
  } catch (e) {
    console.error(e)
  }
}

async function removeStock(stockCode: string) {
  try {
    await store.removeStock(stockCode)
  } catch (e) {
    console.error(e)
  }
}
</script>

<template>
  <div class="history-view">
    <div class="page-header">
      <div class="header-title">
        <el-icon><Collection /></el-icon>
        <span>历史股票</span>
      </div>
      <div class="header-actions">
        <el-button
          v-if="!batchState.isLoading.value"
          type="success"
          size="small"
          :disabled="store.watchlist.length === 0 || batchDebouncePending"
          @click="batchQuickAnalyze"
        >
          <el-icon><DataAnalysis /></el-icon>
          <span>一键分析 ({{ store.watchlist.length }})</span>
        </el-button>
        <el-button
          v-else
          type="danger"
          size="small"
          @click="cancelBatch"
        >
          <el-icon><Close /></el-icon>
          <span>取消分析</span>
        </el-button>
        <el-button type="primary" size="small" class="add-btn" @click="openAddDialog">
          <el-icon><Plus /></el-icon>
          <span>添加股票</span>
        </el-button>
      </div>
    </div>

    <div v-if="batchState.isLoading.value" class="batch-progress">
      <div class="progress-header">
        <span class="progress-title">批量分析中</span>
        <span class="progress-stats font-mono">
          {{ store.batchProgress.current }}/{{ store.batchProgress.total }}
          <span class="progress-pct">{{ batchPercentage }}%</span>
        </span>
      </div>
      <el-progress
        :percentage="batchPercentage"
        :stroke-width="20"
        status="success"
        striped
        striped-flow
        :show-text="false"
      />
      <div class="progress-footer">
        <span class="progress-current" v-if="store.batchProgress.currentStock">
          正在分析: {{ store.batchProgress.currentStock }}
        </span>
        <span class="progress-time">
          <span v-if="batchElapsed">已用 {{ batchElapsed }}</span>
          <span v-if="batchEta" class="progress-eta"> · 预计剩余 {{ batchEta }}</span>
        </span>
      </div>
      <div v-if="store.batchErrorStocks.length > 0" class="progress-errors">
        <span class="error-label">失败股票:</span>
        <span v-for="(err, idx) in store.batchErrorStocks" :key="idx" class="error-item">
          {{ err.stock_input }}: {{ err.error }}
        </span>
      </div>
    </div>

    <div v-if="batchState.isError.value" class="batch-error-banner">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ batchState.error.value }}</span>
      <el-button type="danger" size="small" text @click="batchQuickAnalyze">
        <el-icon><RefreshRight /></el-icon>
        <span>重试</span>
      </el-button>
    </div>

    <div v-if="batchState.isSuccess.value" class="batch-success-banner">
      <el-icon><CircleCheckFilled /></el-icon>
      <span>批量分析完成，共 {{ store.batchProgress.total }} 只股票</span>
      <el-button size="small" text @click="batchState.reset()">
        <el-icon><Close /></el-icon>
        <span>关闭</span>
      </el-button>
    </div>

    <div class="stock-grid">
      <div
        v-for="item in store.watchlist"
        :key="item.stock_code"
        class="stock-card"
        @click="analyzeStock(item)"
      >
        <div class="card-top">
          <div class="stock-info">
            <span class="stock-code font-mono">{{ item.stock_code }}</span>
            <span class="stock-name">{{ item.stock_name }}</span>
          </div>
          <el-tag
            :type="item.position_status === '已持有' ? 'success' : 'info'"
            size="small"
            effect="dark"
            class="status-tag"
          >
            {{ item.position_status }}
          </el-tag>
        </div>
        <div v-if="item.position_status === '已持有' && item.cost_price" class="card-cost">
          <span class="cost-label">成本价</span>
          <span class="cost-value font-mono">{{ item.cost_price.toFixed(2) }}</span>
        </div>
        <div v-if="item.cached_signal" class="card-signal">
          <span
            class="signal-badge"
            :class="getSignalClass(item.cached_signal)"
          >
            {{ item.cached_signal }}
          </span>
          <span v-if="item.cached_signal_score" class="signal-score font-mono">
            {{ item.cached_signal_score.toFixed(2) }}
          </span>
          <span v-if="item.cached_signal_time" class="signal-time">
            {{ new Date(item.cached_signal_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
          </span>
        </div>
        <div class="card-actions">
          <el-button type="primary" size="small" text class="action-btn" @click.stop="analyzeStock(item)">
            <el-icon><TrendCharts /></el-icon>
            <span>分析</span>
          </el-button>
          <el-button size="small" text class="action-btn edit" @click.stop="openEdit(item)">
            <el-icon><Edit /></el-icon>
            <span>编辑</span>
          </el-button>
          <el-button type="danger" size="small" text class="action-btn delete" @click.stop="removeStock(item.stock_code)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="store.watchlist.length === 0" class="empty-state">
      <el-icon class="empty-icon"><DocumentDelete /></el-icon>
      <span class="empty-text">暂无历史股票</span>
      <el-button type="primary" size="small" @click="openAddDialog">添加第一只股票</el-button>
    </div>

    <!-- 添加对话框 -->
    <el-dialog v-model="dialogVisible" title="添加股票" width="420px" class="dark-dialog">
      <el-form label-width="80px">
        <el-form-item label="股票代码">
          <el-input v-model="newStock.stock_input" placeholder="输入股票代码或名称" />
        </el-form-item>
        <el-form-item label="持仓状态">
          <el-select v-model="newStock.position_status">
            <el-option label="未持有" value="未持有" />
            <el-option label="已持有" value="已持有" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="newStock.position_status === '已持有'" label="成本价">
          <el-input-number v-model="newStock.cost_price" :precision="2" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑股票" width="420px" class="dark-dialog">
      <el-form label-width="80px" v-if="editingStock">
        <el-form-item label="股票代码">
          <el-input v-model="editingStock.stock_code" disabled />
        </el-form-item>
        <el-form-item label="持仓状态">
          <el-select v-model="editingStock.position_status" @change="onEditPositionChange">
            <el-option label="未持有" value="未持有" />
            <el-option label="已持有" value="已持有" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editingStock.position_status === '已持有'" label="成本价">
          <el-input-number v-model="editingStock.cost_price" :precision="2" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.history-view {
  max-width: 1400px;
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

.add-btn {
  background: linear-gradient(135deg, var(--color-up, #26a69a) 0%, #00897b 100%) !important;
  border: none !important;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.batch-progress {
  margin: 12px 0;
  padding: 16px 20px;
  background: var(--surface-2, #1a1a1a);
  border: 1px solid rgba(0, 212, 170, 0.15);
  border-radius: var(--radius-md, 10px);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.progress-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.progress-stats {
  font-size: 13px;
  color: var(--color-up, #26a69a);
  font-weight: 600;
}

.progress-pct {
  margin-left: 6px;
  font-size: 15px;
}

.progress-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.progress-current {
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  font-weight: 500;
}

.progress-time {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.progress-eta {
  color: var(--color-up, #26a69a);
  opacity: 0.8;
}

.progress-errors {
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(255, 71, 87, 0.08);
  border-radius: var(--radius-sm, 6px);
  font-size: 11px;
  color: var(--color-down, #ef5350);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.error-label {
  font-weight: 600;
  margin-right: 4px;
}

.error-item {
  padding: 1px 6px;
  background: rgba(255, 71, 87, 0.12);
  border-radius: 3px;
}

.batch-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
  padding: 12px 16px;
  background: rgba(255, 71, 87, 0.08);
  border: 1px solid rgba(255, 71, 87, 0.2);
  border-radius: var(--radius-md);
  color: var(--color-down);
  font-size: 13px;
  font-weight: 500;
}

.batch-success-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
  padding: 12px 16px;
  background: rgba(0, 212, 170, 0.06);
  border: 1px solid rgba(0, 212, 170, 0.15);
  border-radius: var(--radius-md);
  color: var(--color-up);
  font-size: 13px;
  font-weight: 500;
}

.signal-time {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-size: 11px;
  margin-left: 4px;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.stock-card {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 20px;
  cursor: pointer;
  transition: var(--transition-base, 0.25s ease);
  position: relative;
  overflow: hidden;
}

.stock-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--color-up, #26a69a), var(--color-accent, #42a5f5));
  opacity: 0;
  transition: var(--transition-base, 0.25s ease);
}

.stock-card:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
  transform: translateY(-2px);
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.5));
}

.stock-card:hover::before {
  opacity: 1;
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.stock-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stock-code {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  letter-spacing: -0.02em;
}

.stock-name {
  font-size: 13px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.status-tag {
  font-size: 10px;
  height: 20px;
  padding: 0 8px;
}

.card-cost {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--bg-secondary, #1a1a1a);
  border-radius: var(--radius-sm, 6px);
}

.card-signal {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.signal-badge {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 4px;
  letter-spacing: 0.02em;
}

.signal-badge.signal-bull {
  background: rgba(38, 166, 154, 0.15);
  color: var(--color-up, #26a69a);
}

.signal-badge.signal-bear {
  background: rgba(239, 83, 80, 0.15);
  color: var(--color-down, #ef5350);
}

.signal-badge.signal-neutral {
  background: rgba(255, 167, 38, 0.15);
  color: var(--color-warn, #ffa726);
}

.signal-badge.signal-info {
  background: rgba(33, 150, 243, 0.15);
  color: #42a5f5;
}

.signal-score {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.cost-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.cost-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-warn, #ffa726);
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: var(--transition-fast, 0.15s ease);
}

.stock-card:hover .card-actions {
  opacity: 1;
}

.action-btn {
  padding: 4px 10px;
  height: 28px;
  font-size: 12px;
}

.action-btn.edit {
  color: var(--text-secondary, rgba(255, 255, 255, 0.60)) !important;
}

.action-btn.edit:hover {
  color: var(--text-primary, rgba(255, 255, 255, 0.92)) !important;
  background: var(--bg-hover, #262626) !important;
}

.action-btn.delete {
  color: var(--text-muted, rgba(255, 255, 255, 0.38)) !important;
}

.action-btn.delete:hover {
  color: var(--color-down, #ef5350) !important;
  background: rgba(255, 71, 87, 0.1) !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  gap: 16px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.empty-icon {
  font-size: 48px;
  opacity: 0.3;
}

.empty-text {
  font-size: 14px;
}

@media (max-width: 768px) {
  .stock-grid {
    grid-template-columns: 1fr;
  }
  .card-actions {
    opacity: 1;
  }
}
</style>
