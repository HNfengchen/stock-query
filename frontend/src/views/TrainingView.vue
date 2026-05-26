<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, RefreshRight, DataAnalysis, SetUp, Delete, Search } from '@element-plus/icons-vue'
import {
  startTrainingStream,
  getTrainingStatus,
  getModels,
  deleteModel,
  type TrainingMode,
  type ModelInfo,
  type HmmInfo,
} from '@/api/training'

// 训练状态
const isTraining = ref(false)
const selectedMode = ref<TrainingMode>('incremental')
const abortController = ref<AbortController | null>(null)

// 模型数据
const models = ref<ModelInfo[]>([])
const hmmInfo = ref<HmmInfo>({ exists: false, trained_at: null })
const totalModels = ref(0)
const searchQuery = ref('')

// 日志
interface LogEntry {
  msg: string
  level: string
  time: string
}
const logs = ref<LogEntry[]>([])
const MAX_LOG_LINES = 200
const logContainer = ref<HTMLElement | null>(null)

const modeOptions: { mode: TrainingMode; label: string; desc: string; icon: any }[] = [
  { mode: 'incremental', label: '增量训练', desc: '仅训练缺失模型，跳过已存在的模型', icon: Upload },
  { mode: 'force', label: '强制重训', desc: '删除所有模型后重新训练', icon: RefreshRight },
  { mode: 'hmm_only', label: 'HMM训练', desc: '仅训练市场状态识别模型', icon: DataAnalysis },
]

const filteredModels = ref<ModelInfo[]>([])

function updateFilteredModels() {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) {
    filteredModels.value = models.value
  } else {
    filteredModels.value = models.value.filter(m => m.stock_code.toLowerCase().includes(q))
  }
}

async function fetchModels() {
  try {
    const res = await getModels()
    models.value = res.models || []
    hmmInfo.value = res.hmm || { exists: false, trained_at: null }
    totalModels.value = res.total || 0
    updateFilteredModels()
  } catch {
    // 静默处理
  }
}

function addLog(msg: string, level: string) {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  logs.value.push({ msg, level, time })
  if (logs.value.length > MAX_LOG_LINES) {
    logs.value = logs.value.slice(-MAX_LOG_LINES)
  }
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

async function startTraining() {
  if (isTraining.value) return

  isTraining.value = true
  logs.value = []
  addLog(`开始${modeOptions.find(m => m.mode === selectedMode.value)?.label || selectedMode.value}...`, 'info')

  abortController.value = new AbortController()

  await startTrainingStream(
    selectedMode.value,
    (msg, level) => addLog(msg, level),
    (stock, status) => addLog(`[${stock}] ${status}`, 'info'),
    (summary) => {
      isTraining.value = false
      abortController.value = null
      addLog(`训练完成: 成功=${summary.success_count}, 失败=${summary.failed_count}, 跳过=${summary.skipped_count}`, 'info')
      ElMessage.success('训练完成')
      fetchModels()
    },
    (msg) => {
      isTraining.value = false
      abortController.value = null
      addLog(`错误: ${msg}`, 'error')
      ElMessage.error(msg)
    },
    abortController.value.signal,
  )
}

function stopTraining() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
    isTraining.value = false
    addLog('训练已取消', 'warning')
  }
}

async function handleDeleteModel(stockCode: string) {
  try {
    await deleteModel(stockCode)
    ElMessage.success(`已删除 ${stockCode} 模型`)
    fetchModels()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function checkTrainingStatus() {
  try {
    const status = await getTrainingStatus()
    if (status.running) {
      isTraining.value = true
      addLog(`检测到正在进行的训练 (模式: ${status.mode})`, 'warning')
    }
  } catch {
    // 静默处理
  }
}

onMounted(() => {
  fetchModels()
  checkTrainingStatus()
})

onUnmounted(() => {
  if (abortController.value) {
    abortController.value.abort()
  }
})
</script>

<template>
  <div class="training-view">
    <div class="page-header">
      <div class="header-title">
        <el-icon><SetUp /></el-icon>
        <span>模型训练</span>
      </div>
    </div>

    <div class="training-layout">
      <!-- 左栏：训练控制 -->
      <div class="control-panel">
        <div class="section-title">训练模式</div>
        <div class="mode-cards">
          <div
            v-for="opt in modeOptions"
            :key="opt.mode"
            class="mode-card"
            :class="{ active: selectedMode === opt.mode }"
            @click="selectedMode = opt.mode"
          >
            <el-icon class="mode-icon"><component :is="opt.icon" /></el-icon>
            <div class="mode-info">
              <span class="mode-label">{{ opt.label }}</span>
              <span class="mode-desc">{{ opt.desc }}</span>
            </div>
          </div>
        </div>

        <el-popconfirm
          v-if="selectedMode === 'force'"
          title="强制重训将删除所有模型后重新训练，确定继续？"
          confirm-button-text="确定"
          cancel-button-text="取消"
          @confirm="startTraining"
        >
          <template #reference>
            <el-button
              type="primary"
              class="train-btn"
              :loading="isTraining"
              :disabled="isTraining"
            >
              <el-icon v-if="!isTraining"><SetUp /></el-icon>
              <span>{{ isTraining ? '训练中...' : '强制重训' }}</span>
            </el-button>
          </template>
        </el-popconfirm>
        <template v-else>
          <el-button
            type="primary"
            class="train-btn"
            :loading="isTraining"
            :disabled="isTraining && !abortController"
            @click="isTraining ? stopTraining() : startTraining()"
          >
            <el-icon v-if="!isTraining"><SetUp /></el-icon>
            <span>{{ isTraining ? '停止训练' : '开始训练' }}</span>
          </el-button>
        </template>

        <div v-if="isTraining" class="training-status">
          <span class="status-dot running" />
          <span>训练进行中</span>
        </div>

        <div class="section-title" style="margin-top: 20px;">训练日志</div>
        <div ref="logContainer" class="log-area">
          <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
          <div
            v-for="(log, idx) in logs"
            :key="idx"
            class="log-line"
            :class="`log-${log.level}`"
          >
            <span class="log-time">{{ log.time }}</span>
            <span class="log-msg">{{ log.msg }}</span>
          </div>
        </div>
      </div>

      <!-- 右栏：模型展示 -->
      <div class="model-panel">
        <!-- HMM模型状态 -->
        <div class="hmm-card">
          <div class="hmm-header">
            <span class="hmm-title">HMM 市场状态模型</span>
            <el-tag v-if="hmmInfo.exists" type="success" size="small" effect="dark">已训练</el-tag>
            <el-tag v-else type="info" size="small" effect="dark">未训练</el-tag>
          </div>
          <div v-if="hmmInfo.exists && hmmInfo.trained_at" class="hmm-meta">
            <span class="meta-label">训练时间</span>
            <span class="meta-value font-mono">{{ hmmInfo.trained_at }}</span>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="stats-row">
          <div class="stat-item">
            <span class="stat-label">模型总数</span>
            <span class="stat-value font-mono">{{ totalModels }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">最新训练时间</span>
            <span class="stat-value font-mono">{{ models.length > 0 ? models[0]!.trained_at : '-' }}</span>
          </div>
        </div>

        <!-- 个股模型表格 -->
        <div class="table-section">
          <div class="table-header">
            <span class="table-title">个股模型列表</span>
            <el-input
              v-model="searchQuery"
              placeholder="搜索股票代码"
              :prefix-icon="Search"
              size="small"
              clearable
              class="search-input"
              @input="updateFilteredModels"
            />
          </div>
          <el-table :data="filteredModels" size="small" class="dark-table" max-height="500">
            <el-table-column prop="stock_code" label="股票代码" width="120" />
            <el-table-column prop="trained_at" label="训练时间" min-width="180" />
            <el-table-column prop="n_features" label="特征数" width="90" />
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-popconfirm
                  :title="`确定删除 ${row.stock_code} 的模型？`"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleDeleteModel(row.stock_code)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" text :icon="Delete" />
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.training-view {
  max-width: 1600px;
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

.training-layout {
  display: grid;
  grid-template-columns: 2fr 3fr;
  gap: 20px;
}

.control-panel {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 20px;
  height: fit-content;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  margin-bottom: 12px;
  padding-left: 10px;
  border-left: 3px solid var(--color-up, #26a69a);
}

.mode-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.mode-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  cursor: pointer;
  transition: var(--transition-fast, 0.15s ease);
}

.mode-card:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
  background: rgba(0, 212, 170, 0.03);
}

.mode-card.active {
  border-color: var(--color-up, #26a69a);
  background: rgba(0, 212, 170, 0.08);
}

.mode-icon {
  font-size: 20px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  flex-shrink: 0;
}

.mode-card.active .mode-icon {
  color: var(--color-up, #26a69a);
}

.mode-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mode-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.mode-desc {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.train-btn {
  width: 100%;
  background: linear-gradient(135deg, var(--color-up, #26a69a) 0%, var(--color-accent, #42a5f5) 100%) !important;
  border: none !important;
  font-weight: 600;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: var(--transition-base, 0.25s ease);
}

.train-btn:hover {
  background: linear-gradient(135deg, #4db6ac 0%, #1e88e5 100%) !important;
  box-shadow: 0 4px 16px rgba(0, 212, 170, 0.3) !important;
  transform: translateY(-1px);
}

.training-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(0, 212, 170, 0.06);
  border: 1px solid rgba(0, 212, 170, 0.15);
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  color: var(--color-up, #26a69a);
  font-weight: 500;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.status-dot.running {
  background: var(--color-up, #26a69a);
  box-shadow: 0 0 6px rgba(0, 212, 170, 0.5);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 日志区域 - 终端风格 */
.log-area {
  background: #0a0e1a;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-sm, 6px);
  padding: 12px;
  height: 320px;
  overflow-y: auto;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-area::-webkit-scrollbar {
  width: 4px;
}

.log-area::-webkit-scrollbar-track {
  background: transparent;
}

.log-area::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

.log-empty {
  color: var(--text-disabled, rgba(255, 255, 255, 0.22));
  text-align: center;
  padding: 40px 0;
}

.log-line {
  display: flex;
  gap: 8px;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-time {
  color: var(--text-disabled, rgba(255, 255, 255, 0.22));
  flex-shrink: 0;
}

.log-msg {
  color: rgba(255, 255, 255, 0.85);
}

.log-info .log-msg {
  color: rgba(255, 255, 255, 0.85);
}

.log-warning .log-msg {
  color: #f59e0b;
}

.log-error .log-msg {
  color: var(--color-down, #ef5350);
}

/* 右栏 */
.model-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hmm-card {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
  transition: var(--transition-fast, 0.15s ease);
}

.hmm-card:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.hmm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.hmm-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, rgba(255, 255, 255, 0.92));
}

.hmm-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-label {
  font-size: 12px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
}

.meta-value {
  font-size: 12px;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
}

.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat-item {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: var(--transition-fast, 0.15s ease);
}

.stat-item:hover {
  border-color: var(--border-active, rgba(38, 166, 154, 0.4));
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-up, #26a69a);
  letter-spacing: -0.02em;
}

.table-section {
  background: var(--bg-card, #1e1e1e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 10px);
  padding: 16px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
}

.table-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  padding-left: 10px;
  border-left: 3px solid var(--color-up, #26a69a);
}

.search-input {
  width: 200px;
}

@media (max-width: 1200px) {
  .training-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  .search-input {
    width: 140px;
  }
}
</style>
