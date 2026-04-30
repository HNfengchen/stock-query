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
      <el-icon class="logo-icon"><TrendCharts /></el-icon>
      <span class="logo-text">StockQuery</span>
    </div>
    <nav class="nav-menu">
      <div
        v-for="item in navItems"
        :key="item.name"
        class="nav-item"
        :class="{ active: route.name === item.name }"
        @click="navigate(item.path)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>
    </nav>
    <div class="nav-right">
      <el-icon class="theme-icon"><Moon /></el-icon>
    </div>
  </header>
</template>

<style scoped>
.nav-header {
  height: 64px;
  background: linear-gradient(135deg, #1a1f2e 0%, #0f1419 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  padding: 0 32px;
  position: sticky;
  top: 0;
  z-index: 1000;
  backdrop-filter: blur(20px);
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-right: 48px;
}

.logo-icon {
  font-size: 28px;
  color: #00d4aa;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #00d4aa 0%, #00a8e8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.nav-menu {
  display: flex;
  gap: 8px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  color: #8b92a8;
  font-size: 14px;
  font-weight: 500;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e0e6ed;
}

.nav-item.active {
  background: rgba(0, 212, 170, 0.1);
  color: #00d4aa;
  box-shadow: 0 0 20px rgba(0, 212, 170, 0.1);
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.theme-icon {
  font-size: 20px;
  color: #8b92a8;
  cursor: pointer;
  transition: color 0.3s;
}

.theme-icon:hover {
  color: #e0e6ed;
}

@media (max-width: 768px) {
  .nav-header {
    padding: 0 16px;
  }
  .logo-text {
    display: none;
  }
  .nav-item span {
    display: none;
  }
}
</style>
