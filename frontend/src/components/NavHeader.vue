<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const navItems = [
  { path: '/', name: 'analysis', label: '分析报告', icon: 'TrendCharts' },
  { path: '/backtest', name: 'backtest', label: '回测中心', icon: 'DataAnalysis' },
  { path: '/history', name: 'history', label: '历史股票', icon: 'Collection' },
]

function navigate(path: string) {
  router.push(path)
}
</script>

<template>
  <header class="nav-header">
    <div class="logo-section">
      <div class="logo-icon">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <rect width="32" height="32" rx="8" fill="url(#logoGrad)" opacity="0.15"/>
          <path d="M8 22L14 14L18 18L24 8" stroke="url(#logoGrad)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          <defs>
            <linearGradient id="logoGrad" x1="0" y1="0" x2="32" y2="32">
              <stop stop-color="#26a69a"/>
              <stop offset="1" stop-color="#42a5f5"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
      <div class="logo-text">
        <span class="logo-main">StockQuery</span>
        <span class="logo-sub">量化分析系统</span>
      </div>
    </div>
    <nav class="nav-menu">
      <div
        v-for="item in navItems"
        :key="item.name"
        class="nav-item"
        :class="{ active: route.name === item.name }"
        @click="navigate(item.path)"
      >
        <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
        <span class="nav-label">{{ item.label }}</span>
        <div v-if="route.name === item.name" class="nav-indicator" />
      </div>
    </nav>
    <div class="nav-right">
      <div class="market-status">
        <span class="status-dot" />
        <span class="status-text">交易中</span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.nav-header {
  height: 56px;
  background: rgba(10, 14, 26, 0.85);
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
  display: flex;
  align-items: center;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 1000;
  backdrop-filter: blur(20px) saturate(1.2);
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-right: 48px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.logo-main {
  font-size: 16px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--color-up, #26a69a) 0%, var(--color-accent, #42a5f5) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
}

.logo-sub {
  font-size: 10px;
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-weight: 500;
  letter-spacing: 0.08em;
}

.nav-menu {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: var(--transition-base, 0.25s ease);
  color: var(--text-muted, rgba(255, 255, 255, 0.38));
  font-size: 13px;
  font-weight: 500;
}

.nav-item:hover {
  color: var(--text-secondary, rgba(255, 255, 255, 0.60));
  background: rgba(255, 255, 255, 0.03);
}

.nav-item.active {
  color: var(--color-up, #26a69a);
  background: rgba(0, 212, 170, 0.06);
}

.nav-icon {
  font-size: 16px;
}

.nav-label {
  position: relative;
  z-index: 1;
}

.nav-indicator {
  position: absolute;
  bottom: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  height: 2px;
  background: linear-gradient(90deg, var(--color-up, #26a69a), var(--color-accent, #42a5f5));
  border-radius: 1px;
  box-shadow: 0 0 8px rgba(0, 212, 170, 0.4);
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.market-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(0, 212, 170, 0.08);
  border: 1px solid rgba(0, 212, 170, 0.15);
  border-radius: 20px;
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--color-up, #26a69a);
  border-radius: 50%;
  box-shadow: 0 0 6px rgba(0, 212, 170, 0.5);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 11px;
  color: var(--color-up, #26a69a);
  font-weight: 600;
}

@media (max-width: 768px) {
  .nav-header {
    padding: 0 16px;
  }
  .logo-sub {
    display: none;
  }
  .nav-label {
    display: none;
  }
  .market-status {
    display: none;
  }
}
</style>
