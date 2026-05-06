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
  try {
    await store.addStock(newStock.value)
    dialogVisible.value = false
  } catch (e) {
    console.error(e)
  }
}

async function confirmRemove(stockCode: string) {
  try {
    await store.removeStock(stockCode)
  } catch (e) {
    console.error(e)
  }
}

function analyzeStock(item: any) {
  const query: Record<string, string> = { code: item.stock_code }
  if (item.position_status) {
    query.position = item.position_status
  }
  if (item.cost_price) {
    query.cost = String(item.cost_price)
  }
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
</script>

<template>
  <div class="history-view">
    <div class="page-header">
      <h2>历史股票管理</h2>
      <div class="header-actions">
        <el-button @click="openAddDialog">
          <el-icon><Plus /></el-icon> 添加股票
        </el-button>
      </div>
    </div>

    <div class="stock-grid">
      <div
        v-for="item in store.watchlist"
        :key="item.stock_code"
        class="stock-card"
        @click="openEdit(item)"
      >
        <div class="card-header">
          <span class="card-code">{{ item.stock_code }}</span>
          <span class="card-name">{{ item.stock_name }}</span>
        </div>
        <div class="card-info">
          <el-tag :type="item.position_status === '已持有' ? 'success' : 'info'" size="small">
            {{ item.position_status }}
          </el-tag>
          <span v-if="item.cost_price" class="card-cost">成本: {{ item.cost_price }}</span>
          <span v-else class="card-cost">成本: -</span>
        </div>
        <div class="card-actions">
          <el-button type="primary" size="small" text @click.stop="analyzeStock(item)">
            分析
          </el-button>
          <el-button type="danger" size="small" text @click.stop="confirmRemove(item.stock_code)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="store.watchlist.length === 0" class="empty-state">
      <el-icon class="empty-icon"><DocumentDelete /></el-icon>
      <h3>暂无历史股票</h3>
      <p>点击右上角添加股票开始追踪</p>
    </div>

    <!-- 添加股票对话框 -->
    <el-dialog v-model="dialogVisible" title="添加股票" width="400px" class="dark-dialog">
      <el-form label-position="top">
        <el-form-item label="股票代码/名称">
          <el-input v-model="newStock.stock_input" placeholder="如 603956" />
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
    <el-dialog v-model="editDialogVisible" title="编辑股票" width="400px" class="dark-dialog">
      <el-form v-if="editingStock" label-position="top">
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
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 22px;
  font-weight: 600;
  color: #e0e6ed;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.stock-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.stock-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(0, 212, 170, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.card-code {
  font-size: 18px;
  font-weight: 700;
  color: #00d4aa;
}

.card-name {
  font-size: 14px;
  color: #8b92a8;
}

.card-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.card-cost {
  font-size: 13px;
  color: #f0a030;
}

.card-actions {
  display: flex;
  gap: 4px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: #8b92a8;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  color: rgba(0, 212, 170, 0.3);
}

.empty-state h3 {
  font-size: 18px;
  color: #e0e6ed;
  margin-bottom: 8px;
}

.dialog-hint {
  font-size: 13px;
  color: #8b92a8;
  margin-bottom: 12px;
}

.dark-dialog :deep(.el-dialog) {
  background: #1a1f2e;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.dark-dialog :deep(.el-dialog__title) {
  color: #e0e6ed;
}

.dark-dialog :deep(.el-form-item__label) {
  color: #8b92a8;
}

.dark-dialog :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1);
}

.dark-dialog :deep(.el-input__inner) {
  color: #e0e6ed;
}

.dark-dialog :deep(.el-textarea__inner) {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  color: #e0e6ed;
}
</style>
