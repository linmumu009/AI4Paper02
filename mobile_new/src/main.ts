import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initTheme } from '@shared/stores/theme'
import { initBilingualTheme } from '@shared/composables/useBilingualTheme'
import './style.css'

// Vant feedback styles (Toast / Dialog / Notify APIs are imported where used)
import 'vant/es/toast/style'
import 'vant/es/dialog/style'
import 'vant/es/notify/style'

initTheme()
initBilingualTheme()

const app = createApp(App)
app.use(router)
app.mount('#app')
