import axios from 'axios'

/**
 * Browser-native axios instance for shared API usage.
 * No Tauri IPC adapter — works in both the web app and mobile app.
 *
 * In the Tauri desktop app, View/src/api wraps this with tauriAdapter.
 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,
  headers: { 'Cache-Control': 'no-cache' },
})

// Emit 'auth-required' event on 401 for KB/auth-gated endpoints
http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    const isKbEndpoint = url.startsWith('/kb') || url.includes('/kb/')
    if (status === 401 && isKbEndpoint) {
      window.dispatchEvent(new CustomEvent('auth-required'))
    }
    return Promise.reject(error)
  },
)
