import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
// @ts-ignore
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

import App from './App.vue'
import router from './router'
import { initLogging, logPageView, getLogger } from './utils/logger'

const logger = getLogger('app')

initLogging({
  level: import.meta.env.VITE_LOG_LEVEL || 'INFO',
  remoteEndpoint: import.meta.env.VITE_LOG_ENDPOINT || undefined,
})

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn, size: 'default', zIndex: 3000 })

router.afterEach((to) => {
  logPageView(to.path, to.name?.toString())
})

app.mount('#app')

logger.info('Application mounted')
