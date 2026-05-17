<script setup lang="ts">
import { RouterView } from 'vue-router'
import NavHeader from './components/NavHeader.vue'
import SideWatchlist from './components/SideWatchlist.vue'
import { ref } from 'vue'
import { useStockStore } from './stores/stockStore'

const sidebarCollapsed = ref(false)
const stockStore = useStockStore()
</script>

<template>
  <div class="app-container">
    <NavHeader />
    <div class="main-layout">
      <SideWatchlist v-if="!stockStore.cockpitMode" v-model:collapsed="sidebarCollapsed" />
      <main class="content-area" :class="{ 'sidebar-collapsed': sidebarCollapsed && !stockStore.cockpitMode, 'cockpit-mode': stockStore.cockpitMode }">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.main-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.content-area {
  flex: 1;
  margin-left: 260px;
  transition: margin-left 0.3s ease;
  padding: 20px;
  overflow-y: auto;
  background: var(--bg-primary);
  min-height: calc(100vh - 56px);
}

.content-area.sidebar-collapsed {
  margin-left: 56px;
}

.content-area.cockpit-mode {
  margin-left: 0;
}

@media (max-width: 768px) {
  .content-area {
    margin-left: 0;
    padding: 16px;
  }
  .content-area.sidebar-collapsed {
    margin-left: 0;
  }
}
</style>
