import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ command }) => ({
  // Production is mounted under /m/, while dev server stays on root path.
  base: command === 'build' ? '/m/' : '/',
  plugins: [
    vue(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@shared': path.resolve(__dirname, '../shared'),
    },
    dedupe: ['vue', 'vue-router', 'axios'],
  },
  optimizeDeps: {
    include: ['axios', 'vue', 'vue-router'],
  },
  server: {
    host: '0.0.0.0',
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
