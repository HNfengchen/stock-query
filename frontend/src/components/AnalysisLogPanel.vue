<template>
  <div class="analysis-log-panel" :class="{ collapsed: isCollapsed }">
    <div class="log-header" @click="toggleCollapse">
      <div class="log-header-left">
        <span class="log-title">运行日志</span>
        <el-tag v-if="logCount > 0" size="small" :type="logCount > 0 ? 'success' : 'info'" effect="dark" round>{{ logCount }}</el-tag>
      </div>
      <div class="log-header-right" @click.stop>
        <el-select v-model="levelFilter" size="small" style="width: 90px" @change="onFilterChange">
          <el-option label="全部" value="ALL" />
          <el-option label="INFO" value="INFO" />
          <el-option label="WARN" value="WARN" />
          <el-option label="ERROR" value="ERROR" />
        </el-select>
        <el-tooltip :content="autoScroll ? '自动滚动中' : '自动滚动已暂停'" placement="top">
          <el-button size="small" :type="autoScroll ? 'primary' : 'default'" :icon="autoScroll ? VideoPlay : VideoPause"
                     @click="autoScroll = !autoScroll" circle />
        </el-tooltip>
        <el-tooltip content="复制日志" placement="top">
          <el-button size="small" @click="copyLogs" circle>
            <el-icon><DocumentCopy /></el-icon>
          </el-button>
        </el-tooltip>
        <el-icon class="collapse-icon" :class="{ 'is-expanded': !isCollapsed }"><ArrowRight /></el-icon>
      </div>
    </div>
    <div v-show="!isCollapsed" class="log-body" ref="logBodyRef">
      <div v-for="(entry, idx) in filteredLogs" :key="idx" class="log-entry" :class="entry.level.toLowerCase()">
        <span class="log-time">{{ entry.timestamp }}</span>
        <span class="log-level-badge" :class="entry.level.toLowerCase()">{{ entry.level }}</span>
        <span class="log-message">{{ entry.message }}</span>
      </div>
      <div v-if="filteredLogs.length === 0" class="log-empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ArrowRight, VideoPlay, VideoPause, DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { LogEntry } from '@/types'

const props = defineProps<{
  logs: LogEntry[]
}>()

const isCollapsed = ref(true)
const autoScroll = ref(true)
const levelFilter = ref('ALL')
const logBodyRef = ref<HTMLElement | null>(null)

const filteredLogs = computed(() => {
  if (levelFilter.value === 'ALL') return props.logs
  return props.logs.filter(entry => entry.level === levelFilter.value)
})

const logCount = computed(() => props.logs.length)

watch(() => props.logs.length, () => {
  if (autoScroll.value && logBodyRef.value && !isCollapsed.value) {
    nextTick(() => {
      if (logBodyRef.value) {
        logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
      }
    })
  }
})

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  if (!isCollapsed.value && autoScroll.value) {
    nextTick(() => {
      if (logBodyRef.value) {
        logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
      }
    })
  }
}

function onFilterChange() {
  if (autoScroll.value && logBodyRef.value && !isCollapsed.value) {
    nextTick(() => {
      if (logBodyRef.value) {
        logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
      }
    })
  }
}

function copyLogs() {
  const text = props.logs.map(entry => `[${entry.timestamp}] [${entry.level}] ${entry.message}`).join('\n')
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('日志已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function expand() {
  isCollapsed.value = false
}

function collapse() {
  isCollapsed.value = true
}

defineExpose({ expand, collapse })
</script>

<style scoped>
.analysis-log-panel {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  background: #1a1d23;
  overflow: hidden;
  transition: all 0.3s ease;
}

.analysis-log-panel.collapsed {
  border-radius: 8px;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #1e2129 0%, #252830 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  transition: background 0.2s;
}

.log-header:hover {
  background: linear-gradient(135deg, #252830 0%, #2c303a 100%);
}

.log-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.log-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  letter-spacing: 0.02em;
}

.log-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-icon {
  color: #888;
  font-size: 14px;
  margin-left: 4px;
  transition: transform 0.3s ease;
}

.collapse-icon.is-expanded {
  transform: rotate(90deg);
}

.log-body {
  max-height: 240px;
  overflow-y: auto;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12px;
  line-height: 1.7;
  padding: 4px 0;
  scroll-behavior: smooth;
}

.log-body::-webkit-scrollbar {
  width: 6px;
}

.log-body::-webkit-scrollbar-track {
  background: transparent;
}

.log-body::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.log-body::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

.log-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 16px;
  transition: background 0.15s;
}

.log-entry:hover {
  background: rgba(255, 255, 255, 0.03);
}

.log-entry.info {
  color: #b0b8c8;
}

.log-entry.warn {
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.06);
}

.log-entry.error {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.08);
}

.log-time {
  color: #6b7280;
  flex-shrink: 0;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  min-width: 64px;
}

.log-level-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.05em;
  min-width: 40px;
  text-align: center;
}

.log-level-badge.info {
  color: #67c23a;
  background: rgba(103, 194, 58, 0.12);
}

.log-level-badge.warn {
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.15);
}

.log-level-badge.error {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.15);
}

.log-message {
  flex: 1;
  word-break: break-word;
  color: inherit;
}

.log-empty {
  text-align: center;
  padding: 24px;
  color: #555;
  font-size: 12px;
}
</style>
