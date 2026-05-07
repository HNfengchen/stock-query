<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStockStore } from '@/stores/stockStore'
import { useRouter } from 'vue-router'
import type { AnalysisRequest } from '@/types'

const store = useStockStore()
const router = useRouter()

const dialogVisible = ref(false)
const editDialogVisible = ref(false)
const editingStock = ref<any>(null)

const newStock = ref<AnalysisRequest>({
  stock_input: '',
  position_status: '未持有',
  cost_price: null,
})

onMounted(() => {
  store.loadWatchlist()
})

function openAddDialog() {
  newStock.value = { stock_input: '', position_status: '未持有', cost_price: null }
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

function analyzeStock(item: any) {
  const query: Record<string, string> = { code: item.stock_code }
  if (item.position_status) query.position = item.position_status
  if (item.cost_price) query.cost = String(item.cost_price)
  router.push({ path: '/', query })
}

function openEdit(item: any) {
  editingStock.value = { ...item }
  editDialogVisible.value = true
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
      <el-button type="primary" size="small" class="add-btn" @click="openAddDialog">
        <el-icon><Plus /></el-icon>
        <span>添加股票</span>
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
        <div v-if="item.cost_price" class="card-cost">
          <span class="cost-label">成本价</span>
          <span class="cost-value font-mono">{{ item.cost_price.toFixed(2) }}</span>
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
          <el-select v-model="editingStock.position_status">
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
  border-bottom: 1px solid var(--border-subtle);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.header-title .el-icon {
  font-size: 22px;
  color: var(--color-up);
}

.add-btn {
  background: linear-gradient(135deg, var(--color-up) 0%, #00897b 100%) !important;
  border: none !important;
  font-weight: 600;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.stock-card {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  cursor: pointer;
  transition: var(--transition-base);
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
  background: linear-gradient(90deg, var(--color-up), var(--color-accent));
  opacity: 0;
  transition: var(--transition-base);
}

.stock-card:hover {
  border-color: var(--border-active);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
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
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.stock-name {
  font-size: 13px;
  color: var(--text-muted);
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
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}

.cost-label {
  font-size: 11px;
  color: var(--text-muted);
}

.cost-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-warn);
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: var(--transition-fast);
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
  color: var(--text-secondary) !important;
}

.action-btn.edit:hover {
  color: var(--text-primary) !important;
  background: var(--bg-hover) !important;
}

.action-btn.delete {
  color: var(--text-muted) !important;
}

.action-btn.delete:hover {
  color: var(--color-down) !important;
  background: rgba(255, 71, 87, 0.1) !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  gap: 16px;
  color: var(--text-muted);
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
