import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initTheme } from './stores/theme'
import { initBilingualTheme } from './composables/useBilingualTheme'
import './style.css'

// 在 Vue mount 前初始化主题和双语配色，避免闪烁
initTheme()
initBilingualTheme()

const app = createApp(App)
app.use(router)
app.mount('#app')
