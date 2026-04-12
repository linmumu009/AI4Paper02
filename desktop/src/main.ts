import { createApp } from 'vue'
import App from '@view/App.vue'
import router from '@view/router'
import { initTheme } from '@view/stores/theme'
import { initBilingualTheme } from '@view/composables/useBilingualTheme'
import '@view/style.css'

initTheme()
initBilingualTheme()

const app = createApp(App)
app.use(router)
app.mount('#app')
