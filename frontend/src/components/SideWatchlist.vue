<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStockStore } from '@/stores/stockStore'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { WatchlistItem } from '@/types'

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

function analyzeStock(item: WatchlistItem) {
  const query: Record<string, string> = { code: item.stock_code }
  if (item.position_status) {
    query.position = item.position_status
  }
  if (item.position_status === '已持有' && item.cost_price) {
    query.cost = String(item.cost_price)
  }
  router.push({ path: '/', query })
}

async function removeStock(stockCode: string, event: Event) {
  event.stopPropagation()
  try {
    await store.removeStock(stockCode)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="header-title" v-if="!collapsed">
        <el-icon class="header-icon"><Collection /></el-icon>
        <span>关注列表</span>
      </div>
      <el-icon class="collapse-btn" @click="toggleCollapse">
        <Fold v-if="!collapsed" />
        <Expand v-else />
      </el-icon>
    </div>
    <div v-if="!collapsed" class="watchlist-content">
      <div
        v-for="item in store.watchlist"
        :key="item.stock_code"
        class="watchlist-item"
        @click="analyzeStock(item)"
      >
        <div class="item-main">
          <div class="item-top">
            <span class="stock-code">{{ item.stock_code }}</span>
            <el-tag
              :type="item.position_status === '已持有' ? 'success' : 'info'"
              size="small"
              effect="dark"
              class="status-tag"
            >
              {{ item.position_status }}
            </el-tag>
          </div>
          <div class="item-bottom">
            <span class="stock-name">{{ item.stock_name }}</span>
            <span v-if="item.position_status === '已持有' && item.cost_price" class="cost-price">
              成本 {{ item.cost_price.toFixed(2) }}
            </span>
          </div>
        </div>
        <div class="item-actions">
          <el-button
            type="primary"
            size="small"
            text
            class="action-btn analyze"
            @click.stop="analyzeStock(item)"
          >
            <el-icon><TrendCharts /></el-icon>
          </el-button>
          <el-button
            type="danger"
            size="small"
            text
            class="action-btn delete"
            @click.stop="removeStock(item.stock_code, $event)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
      <div v-if="store.watchlist.length === 0" class="empty-state">
        <el-icon class="empty-icon"><DocumentDelete /></el-icon>
        <span class="empty-text">暂无关注股票</span>
      </div>
    </div>
    <div v-else class="collapsed-icons">
      <el-tooltip
        v-for="item in store.watchlist.slice(0, 10)"
        :key="item.stock_code"
        :content="`${item.stock_code} ${item.stock_name}`"
        placement="right"
        effect="dark"
      >
        <div
          class="collapsed-item"
          @click="analyzeStock(item)"
        >
          <span class="collapsed-code">{{ item.stock_code.slice(-4) }}</span>
        </div>
      </el-tooltip>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  background: var(--bg-secondary, #1a1a1a);
  border-right: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  position: fixed;
  left: 0;
  top: 56px;
  bottom: 0;
  z-index: 100;
  transition: width 0.3s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar.collapsed {
  width: 56px;
}

.sidebar-header {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
}

.header-icon {
  font-size: 16px;
  color: var(--color-up, #26a69a);
}

.collapse-btn {
  font-size: 14px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  cursor: pointer;
  transition: var(--transition-fast, 0.15s ease);
  padding: 4px;
  border-radius: var(--radius-sm, 6px);
}

.collapse-btn:hover {
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  background: var(--bg-hover, #262626);
}

.watchlist-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.watchlist-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: var(--transition-fast, 0.15s ease);
  border: 1px solid transparent;
  margin-bottom: 4px;
}

.watchlist-item:hover {
  background: var(--bg-hover, #262626);
  border-color: var(--border-default, rgba(255, 255, 255, 0.08));
}

.watchlist-item:hover .item-actions {
  opacity: 1;
}

.item-main {
  flex: 1;
  min-width: 0;
}

.item-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.stock-code {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
  letter-spacing: -0.02em;
}

.status-tag {
  font-size: 10px;
  height: 18px;
  padding: 0 6px;
}

.item-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stock-name {
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cost-price {
  font-size: 11px;
  color: var(--color-warn, #ffa726);
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
  flex-shrink: 0;
}

.item-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: var(--transition-fast, 0.15s ease);
}

.action-btn {
  padding: 4px;
  height: 24px;
  width: 24px;
}

.action-btn.analyze {
  color: var(--color-up, #26a69a);
}

.action-btn.analyze:hover {
  color: #4db6ac;
  background: rgba(0, 212, 170, 0.1);
}

.action-btn.delete {
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.action-btn.delete:hover {
  color: var(--color-down, #ef5350);
  background: rgba(255, 71, 87, 0.1);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  gap: 8px;
}

.empty-icon {
  font-size: 28px;
  opacity: 0.3;
}

.empty-text {
  font-size: 12px;
}

.collapsed-icons {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  gap: 4px;
}

.collapsed-item {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: var(--transition-fast, 0.15s ease);
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.collapsed-item:hover {
  background: var(--bg-hover, #262626);
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.collapsed-code {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
