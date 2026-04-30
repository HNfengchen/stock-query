<script setup lang="ts">
import { RouterView } from 'vue-router'
import NavHeader from './components/NavHeader.vue'
import SideWatchlist from './components/SideWatchlist.vue'
import { ref } from 'vue'

const sidebarCollapsed = ref(false)
</script>

<template>
  <div class="app-container">
    <NavHeader />
    <div class="main-layout">
      <SideWatchlist v-model:collapsed="sidebarCollapsed" />
      <main class="content-area" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
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
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  background: #0a0e1a;
  color: #e0e6ed;
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
  margin-left: 280px;
  transition: margin-left 0.3s ease;
  padding: 24px;
  overflow-y: auto;
  background: #0f1419;
  min-height: calc(100vh - 64px);
}

.content-area.sidebar-collapsed {
  margin-left: 64px;
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
