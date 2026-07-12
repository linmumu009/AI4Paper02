/**
 * BrowserTransport — ApiTransport implementation for web browsers and mobile PWA.
 *
 * - Uses native Axios for REST calls (withCredentials: true, cookie-based auth).
 * - Uses native fetch() for SSE streaming.
 * - Uses fetch + Blob + <a> click for file downloads.
 * - Session token: reads from httpOnly cookie automatically (no manual handling needed).
 */

import axios, { type AxiosInstance } from 'axios'
import type { ApiTransport, StreamConfig, DownloadConfig } from './types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readCookieToken(): string {
  if (typeof document === 'undefined') return ''
  const m = document.cookie.match(/(?:^|;\s*)session_id=([^;]*)/)
  return m ? decodeURIComponent(m[1]) : ''
}

function buildAuthHeaders(token?: string): Record<string, string> {
  const t = token ?? readCookieToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

function normaliseBody(body: unknown): string | undefined {
  if (body === undefined || body === null) return undefined
  return typeof body === 'string' ? body : JSON.stringify(body)
}

function triggerBlobDownload(blob: Blob, fileName: string): void {
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}

function extractFilename(cd: string, fallback: string): string {
  const m = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';\r\n]+)["']?/i)
  return m ? decodeURIComponent(m[1]) : fallback
}

// ---------------------------------------------------------------------------
// BrowserTransport
// ---------------------------------------------------------------------------

export class BrowserTransport implements ApiTransport {
  readonly isTauri = false
  readonly apiOrigin = ''
  readonly axiosInstance: AxiosInstance

  constructor() {
    this.axiosInstance = axios.create({
      baseURL: '/api',
      timeout: 30000,
      withCredentials: true,
      headers: { 'Cache-Control': 'no-cache' },
    })

    // Any protected endpoint can reveal an expired session. Auth endpoints are
    // excluded because failed login/registration is handled by their forms.
    this.axiosInstance.interceptors.response.use(
      (r) => r,
      (error) => {
        const status = error?.response?.status
        const url: string = error?.config?.url || ''
        if (status === 401 && !url.startsWith('/auth') && !url.includes('/auth/')) {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('auth-required'))
          }
        }
        return Promise.reject(error)
      },
    )
  }

  getToken(): string {
    return readCookieToken()
  }

  setToken(_token: string): void {
    // Browser uses httpOnly cookies managed by the server — nothing to store.
  }

  clearToken(): void {
    // Managed by the server (Set-Cookie: session_id=; Max-Age=0)
  }

  async stream(config: StreamConfig): Promise<Response> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...buildAuthHeaders(),
    }
    return fetch(`/api${config.path}`, {
      method: config.method,
      headers,
      credentials: 'include',
      body: normaliseBody(config.body),
      signal: config.signal,
    })
  }

  async download(config: DownloadConfig): Promise<void> {
    const url = `/api${config.path}`
    const token = readCookieToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const resp = await fetch(url, {
      method: config.method || 'GET',
      headers,
      credentials: 'include',
      body: normaliseBody(config.body),
    })

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`
      try {
        const d = await resp.json()
        if (d?.detail) detail = d.detail
      } catch { /* ignore */ }
      throw new Error(`下载失败: ${detail}`)
    }

    const cd = resp.headers.get('content-disposition') || ''
    const fileName = extractFilename(cd, config.fallbackName)
    const blob = await resp.blob()
    triggerBlobDownload(blob, fileName)
  }

  async fetchText(url: string): Promise<string> {
    const resp = await fetch(url, { credentials: 'include' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return resp.text()
  }

  async fetchPdfBlobUrl(url: string): Promise<string> {
    // Browser can use the URL directly in <iframe src>
    return url
  }
}
