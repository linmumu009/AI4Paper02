import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@shared': path.resolve(__dirname, '../shared'),
      'axios': path.resolve(__dirname, 'node_modules/axios'),
    },
  },
  build: {
    // KaTeX is a single prebuilt module (~522 kB minified, ~155 kB gzip).
    // Keep the warning budget just above that isolated, cacheable vendor chunk.
    chunkSizeWarningLimit: 550,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalized = id.replace(/\\/g, '/')
          if (normalized.includes('/node_modules/zrender/')) {
            return 'vendor-zrender'
          }
          if (normalized.includes('/node_modules/echarts/')) {
            return 'vendor-echarts'
          }
          if (
            normalized.includes('/node_modules/@tiptap/')
            || normalized.includes('/node_modules/@prosemirror/')
            || normalized.includes('/node_modules/prosemirror-')
            || normalized.includes('/node_modules/lowlight/')
          ) {
            return 'vendor-editor'
          }
          if (normalized.includes('/node_modules/katex/')) {
            return 'vendor-katex'
          }
          if (normalized.includes('/node_modules/markdown-it')) {
            return 'vendor-markdown'
          }
          if (
            normalized.includes('/node_modules/modern-screenshot/')
            || normalized.includes('/node_modules/qrcode/')
          ) {
            return 'vendor-share'
          }
          if (
            normalized.includes('/node_modules/vue/')
            || normalized.includes('/node_modules/@vue/')
            || normalized.includes('/node_modules/vue-router/')
          ) {
            return 'vendor-vue'
          }
          if (normalized.includes('/node_modules/axios/')) {
            return 'vendor-network'
          }
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (_err, _req, res) => {
            if (res && !res.headersSent && typeof res.writeHead === 'function') {
              res.writeHead(502, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ detail: '后端服务暂时不可用，请稍后刷新' }))
            }
          })
        },
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
