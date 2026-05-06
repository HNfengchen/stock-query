<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStockStore } from '@/stores/stockStore'
import { useRouter } from 'vue-router'

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ (e: 'update:collapsed', v: boolean): void }>()

const store = useStockStore()
const router = useRouter()

onMounted(() => {
  store.loadWatchlist()
})

function toggleCollapse() {
  emit('update:collapsed', !props.collapsed)
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

async function removeStock(stockCode: string, event: Event) {
  event.stopPropagation()
  try {
    await store.removeStock(stockCode)
  } catch (e) {
    console.error(e)
  }
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <el-icon class="watchlist-icon"><Collection /></el-icon>
      <span v-if="!collapsed" class="sidebar-title">历史股票</span>
      <el-icon class="collapse-btn" @click="toggleCollapse"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
    </div>
    <div v-if="!collapsed" class="watchlist-content">
      <div
        v-for="item in store.watchlist"
        :key="item.stock_code"
        class="watchlist-item"
        @click="analyzeStock(item)"
      >
        <div class="item-header">
          <span class="stock-code">{{ item.stock_code }}</span>
          <span class="stock-name">{{ item.stock_name }}</span>
        </div>
        <div class="item-info">
          <el-tag :type="item.position_status === '已持有' ? 'success' : 'info'" size="small">
            {{ item.position_status }}
          </el-tag>
          <span v-if="item.cost_price" class="cost-price">成本: {{ item.cost_price }}</span>
        </div>
        <div class="item-actions">
          <el-button type="primary" size="small" text @click.stop="analyzeStock(item)">
            分析
          </el-button>
          <el-button type="danger" size="small" text @click.stop="removeStock(item.stock_code, $event)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
      <div v-if="store.watchlist.length === 0" class="empty-state">
        <el-icon><DocumentDelete /></el-icon>
        <span>暂无股票</span>
      </div>
    </div>
    <div v-else class="collapsed-icons">
      <el-icon
        v-for="item in store.watchlist.slice(0, 8)"
        :key="item.stock_code"
        class="collapsed-item"
        :title="item.stock_code"
        @click="analyzeStock(item)"
      >
        <Document />
      </el-icon>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  background: #141b2d;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  position: fixed;
  left: 0;
  top: 64px;
  bottom: 0;
  z-index: 100;
  transition: width 0.3s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  gap: 12px;
}

.watchlist-icon {
  font-size: 20px;
  color: #00d4aa;
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: #e0e6ed;
  flex: 1;
}

.collapse-btn {
  font-size: 18px;
  color: #8b92a8;
  cursor: pointer;
  transition: color 0.3s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  color: #e0e6ed;
}

.watchlist-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.watchlist-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.watchlist-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(0, 212, 170, 0.3);
  transform: translateX(4px);
}

.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.stock-code {
  font-size: 14px;
  font-weight: 700;
  color: #00d4aa;
}

.stock-name {
  font-size: 13px;
  color: #8b92a8;
}

.item-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.cost-price {
  font-size: 12px;
  color: #f0a030;
}

.item-actions {
  display: flex;
  gap: 4px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #8b92a8;
  gap: 12px;
}

.empty-state .el-icon {
  font-size: 32px;
}

.collapsed-icons {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  gap: 12px;
}

.collapsed-item {
  font-size: 20px;
  color: #8b92a8;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: all 0.3s;
}

.collapsed-item:hover {
  background: rgba(0, 212, 170, 0.1);
  color: #00d4aa;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
