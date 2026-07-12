/**
 * TauriTransport — ApiTransport implementation for the Tauri desktop app.
 *
 * WebView2 cannot make cross-origin HTTP requests through the DOM, so all
 * network calls are proxied through Rust via the Tauri IPC bridge:
 *   - REST:     direct_request        (JSON ↔ string body)
 *   - Upload:   direct_upload         (multipart/form-data via base64)
 *   - Binary:   direct_download_binary (base64 → Blob URL)
 *   - SSE:      direct_request_stream  (Rust Channel → ReadableStream)
 *
 * Session token is stored in localStorage (cookies are unreliable cross-origin
 * in WebView2) and attached as an Authorization: Bearer header on every request.
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import type { ApiTransport, StreamConfig, DownloadConfig } from './types'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SESSION_TOKEN_KEY = 'ai4papers_session_id'

// ---------------------------------------------------------------------------
// Tauri IPC helpers
// ---------------------------------------------------------------------------

type TauriInvoke = (cmd: string, args?: Record<string, unknown>) => Promise<any>

function getTauriInvoke(): TauriInvoke | null {
  return (window as any).__TAURI_INTERNALS__?.invoke ?? null
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function normaliseApiBase(raw: string): string {
  let s = (raw || '').trim().replace(/\/+$/, '')
  if (s.toLowerCase().endsWith('/api')) s = s.slice(0, -4)
  return s
}

async function fileToBase64(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      const idx = result.indexOf(',')
      resolve(idx >= 0 ? result.slice(idx + 1) : result)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function normaliseBody(body: unknown): string | null {
  if (body === undefined || body === null) return null
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
// Tauri-specific request implementations
// ---------------------------------------------------------------------------

async function tauriDownloadBinary(
  invoke: TauriInvoke,
  url: string,
  headers: Record<string, string>,
  fallbackName: string,
  method = 'GET',
  body: string | null = null,
): Promise<void> {
  const result: { base64: string; content_type: string; file_name: string } =
    await invoke('direct_download_binary', { method, url, headers, body })

  const binary = atob(result.base64)
  const arr = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i)
  const contentType = result.content_type || 'application/octet-stream'
  const fileName = result.file_name || fallbackName
  triggerBlobDownload(new Blob([arr], { type: contentType }), fileName)
}

function tauriStreamResponse(
  invoke: TauriInvoke,
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string | null,
  signal?: AbortSignal,
): Response {
  const encoder = new TextEncoder()
  let ctrl!: ReadableStreamDefaultController<Uint8Array>

  const readable = new ReadableStream<Uint8Array>({
    start(c) { ctrl = c },
  })

  const __TAURI__ = (window as any).__TAURI_INTERNALS__
  // once=false: persistent callback — every Rust channel.send() fires this
  const channelId: number = __TAURI__.transformCallback(
    ({ message }: { message: string }) => {
      try { ctrl.enqueue(encoder.encode(message + '\n')) } catch { /* stream closed */ }
    },
    false,
  )

  if (signal) {
    signal.addEventListener('abort', () => {
      try { ctrl.close() } catch { /* already closed */ }
    }, { once: true })
  }

  invoke('direct_request_stream', {
    method,
    url,
    headers,
    body,
    onEvent: `__CHANNEL__:${channelId}`,
  })
    .then(() => { try { ctrl.close() } catch { /* already closed */ } })
    .catch((err: unknown) => { try { ctrl.error(new Error(String(err))) } catch { /* already errored */ } })

  return new Response(readable, { status: 200 })
}

// ---------------------------------------------------------------------------
// Tauri Axios adapter
// ---------------------------------------------------------------------------

async function tauriAxiosAdapter(config: InternalAxiosRequestConfig): Promise<any> {
  const invoke = getTauriInvoke()
  if (!invoke) throw new Error('Tauri IPC not available')

  // Build full URL
  let fullUrl: string = config.url || ''
  if (config.baseURL && !fullUrl.startsWith('http')) {
    fullUrl = config.baseURL.replace(/\/+$/, '') + '/' + fullUrl.replace(/^\/+/, '')
  }

  // Query params
  if (config.params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(config.params)) {
      if (v !== undefined && v !== null) qs.append(k, String(v))
    }
    const qsStr = qs.toString()
    if (qsStr) fullUrl += (fullUrl.includes('?') ? '&' : '?') + qsStr
  }

  // Headers
  const headers: Record<string, string> = {}
  if (config.headers) {
    const raw = typeof (config.headers as any).toJSON === 'function'
      ? (config.headers as any).toJSON()
      : config.headers
    for (const [k, v] of Object.entries(raw)) {
      if (v !== undefined && v !== null && v !== false) headers[k] = String(v)
    }
  }
  delete headers['User-Agent']

  // FormData path → direct_upload
  if (config.data instanceof FormData) {
    const formData: FormData = config.data
    delete headers['Content-Type']
    delete headers['content-type']

    let fileBase64 = ''
    let fileName = 'upload'
    let mimeType = 'application/octet-stream'
    const formFields: Record<string, string> = {}

    for (const [key, value] of formData.entries()) {
      if (value instanceof File) {
        fileName = value.name || key
        mimeType = value.type || 'application/octet-stream'
        fileBase64 = await fileToBase64(value)
      } else {
        formFields[key] = String(value)
      }
    }

    if (!fileBase64) throw new Error('FormData 中未找到 File 条目')

    const result = await invoke('direct_upload', {
      url: fullUrl, headers, fileName, fileBase64, mimeType, formFields,
    })

    let responseData: any = result.body
    try { responseData = JSON.parse(result.body) } catch { /* keep raw */ }

    const response = {
      data: responseData,
      status: result.status,
      statusText: '',
      headers: result.headers || {},
      config,
      request: {},
    }

    if (result.status >= 400) {
      const error: any = new Error(`Request failed with status code ${result.status}`)
      error.config = config
      error.response = response
      error.isAxiosError = true
      throw error
    }
    return response
  }

  // JSON / text path → direct_request
  let body: string | null = null
  if (config.data !== undefined && config.data !== null) {
    body = typeof config.data === 'string' ? config.data : JSON.stringify(config.data)
    if (!headers['Content-Type'] && !headers['content-type']) {
      headers['Content-Type'] = 'application/json'
    }
  }

  const result = await invoke('direct_request', {
    method: (config.method || 'get').toUpperCase(),
    url: fullUrl,
    headers,
    body,
  })

  let responseData: any = result.body
  try { responseData = JSON.parse(result.body) } catch { /* keep raw */ }

  const response = {
    data: responseData,
    status: result.status,
    statusText: '',
    headers: result.headers || {},
    config,
    request: {},
  }

  if (result.status >= 400) {
    const error: any = new Error(`Request failed with status code ${result.status}`)
    error.config = config
    error.response = response
    error.isAxiosError = true
    throw error
  }

  return response
}

// ---------------------------------------------------------------------------
// TauriTransport
// ---------------------------------------------------------------------------

export class TauriTransport implements ApiTransport {
  readonly isTauri = true
  readonly apiOrigin: string
  readonly axiosInstance: AxiosInstance

  constructor(rawApiBase: string) {
    this.apiOrigin = normaliseApiBase(rawApiBase)

    this.axiosInstance = axios.create({
      baseURL: `${this.apiOrigin}/api`,
      timeout: 30000,
      withCredentials: false,
      headers: { 'Cache-Control': 'no-cache' },
      adapter: tauriAxiosAdapter,
    })

    // Request interceptor: attach Bearer token
    this.axiosInstance.interceptors.request.use((config) => {
      const token = this.getToken()
      if (token && !config.headers['Authorization']) {
        config.headers['Authorization'] = `Bearer ${token}`
      }
      return config
    })

    // Response interceptor: persist session_id on login + expired-session event
    this.axiosInstance.interceptors.response.use(
      (response) => {
        const url: string = response.config?.url || ''
        if (
          (url.includes('/auth/login') || url.includes('/auth/login/sms')) &&
          response.data?.session_id
        ) {
          this.setToken(response.data.session_id)
        }
        return response
      },
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

  // ---- Session token -------------------------------------------------------

  getToken(): string {
    return (typeof localStorage !== 'undefined' && localStorage.getItem(SESSION_TOKEN_KEY)) || ''
  }

  setToken(token: string): void {
    if (typeof localStorage === 'undefined') return
    if (token) {
      localStorage.setItem(SESSION_TOKEN_KEY, token)
    } else {
      localStorage.removeItem(SESSION_TOKEN_KEY)
    }
  }

  clearToken(): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(SESSION_TOKEN_KEY)
    }
  }

  // ---- Stream ---------------------------------------------------------------

  async stream(config: StreamConfig): Promise<Response> {
    const invoke = getTauriInvoke()
    if (!invoke) throw new Error('Tauri IPC not available')

    const token = this.getToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const url = `${this.apiOrigin}/api${config.path}`
    const body = normaliseBody(config.body)

    return tauriStreamResponse(invoke, config.method, url, headers, body, config.signal)
  }

  // ---- Download ------------------------------------------------------------

  async download(config: DownloadConfig): Promise<void> {
    const invoke = getTauriInvoke()
    if (!invoke) throw new Error('Tauri IPC not available')

    const token = this.getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const url = `${this.apiOrigin}/api${config.path}`
    const method = config.method || 'GET'
    const body = normaliseBody(config.body)

    await tauriDownloadBinary(invoke, url, headers, config.fallbackName, method, body)
  }

  // ---- Text / PDF ----------------------------------------------------------

  async fetchText(url: string): Promise<string> {
    const invoke = getTauriInvoke()
    if (!invoke) throw new Error('Tauri IPC not available')
    const token = this.getToken()
    const headers: Record<string, string> = { Accept: '*/*' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const result = await invoke('direct_request', { method: 'GET', url, headers, body: null })
    if (result.status >= 400) throw new Error(`HTTP ${result.status}`)
    return result.body
  }

  async fetchPdfBlobUrl(pdfUrl: string): Promise<string> {
    const invoke = getTauriInvoke()
    if (!invoke) throw new Error('Tauri IPC not available')
    const token = this.getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const result: { base64: string; content_type: string; file_name: string } =
      await invoke('direct_download_binary', { method: 'GET', url: pdfUrl, headers, body: null })
    const binary = atob(result.base64)
    const arr = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/pdf' })
    return URL.createObjectURL(blob)
  }
}
