import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const host = process.env.TAURI_DEV_HOST

function normaliseApiBase(raw: string): string {
  let s = (raw || '').trim().replace(/\/+$/, '')
  if (s.toLowerCase().endsWith('/api')) s = s.slice(0, -4)
  return s
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  if (mode === 'production') {
    const raw = env.VITE_API_BASE || ''
    if (!raw) {
      console.warn(
        '\n⚠️  [Tauri build] VITE_API_BASE is not set in desktop/.env.production!\n' +
        '   Without it every API request will fail in the packaged desktop app.\n' +
        '   Create desktop/.env.production with:\n' +
        '     VITE_API_BASE=https://your-server.com\n',
      )
    }
  }

  const apiTarget = normaliseApiBase(env.VITE_API_BASE) || 'http://127.0.0.1:8000'

  return {
    plugins: [
      vue(),
      tailwindcss(),
    ],
    resolve: {
      dedupe: [
        'vue',
        'vue-router',
        '@vue/reactivity',
        '@vue/runtime-core',
        '@vue/runtime-dom',
        '@vue/shared',
      ],
      alias: {
        '@view': path.resolve(__dirname, '../View/src'),
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      host: host || 'localhost',
      port: 1420,
      strictPort: true,
      hmr: host
        ? { protocol: 'ws', host, port: 1421 }
        : undefined,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/static': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    publicDir: path.resolve(__dirname, '../View/public'),
    envPrefix: ['VITE_', 'TAURI_'],
    build: {
      target: 'chrome105',
      minify: process.env.TAURI_ENV_DEBUG ? false : 'esbuild',
      sourcemap: !!process.env.TAURI_ENV_DEBUG,
    },
  }
})
