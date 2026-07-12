/**
 * ApiClient — the single source of truth for the active transport.
 *
 * Call configureTransport() once at application startup before any API call:
 *
 *   // Tauri desktop (View/src/api/index.ts)
 *   import { configureTransport } from '@shared/api/client'
 *   import { TauriTransport } from '@shared/api/transport/tauri'
 *   if (import.meta.env.VITE_API_BASE) {
 *     configureTransport(new TauriTransport(import.meta.env.VITE_API_BASE))
 *   }
 *
 *   // Browser / mobile — BrowserTransport is the default, no call needed.
 *
 * The `http` export is a Proxy that always delegates to the current transport's
 * Axios instance.  Existing domain modules (shared/api/*.ts) import `http` once
 * at module load and continue to work correctly after configureTransport() swaps
 * the underlying instance, without any re-import.
 */

import type { AxiosInstance } from 'axios'
import { BrowserTransport } from './transport/browser'
import type { ApiTransport, StreamConfig, DownloadConfig } from './transport/types'

// ---------------------------------------------------------------------------
// Active transport — defaults to BrowserTransport
// ---------------------------------------------------------------------------

let _transport: ApiTransport = new BrowserTransport()
let _axiosRef: AxiosInstance = _transport.axiosInstance

/**
 * Replace the active transport.  Must be called before the first API request.
 * In practice this means: top of View/src/api/index.ts or in main.ts.
 */
export function configureTransport(transport: ApiTransport): void {
  _transport = transport
  _axiosRef = transport.axiosInstance
}

// ---------------------------------------------------------------------------
// `http` — Proxy-based dynamic Axios instance
//
// A Proxy is used instead of a direct reference so that `import { http }` in
// domain modules always sees the current underlying instance even after
// configureTransport() is called later.  All property accesses are forwarded
// to _axiosRef which is updated in configureTransport().
// ---------------------------------------------------------------------------

export const http: AxiosInstance = new Proxy({} as AxiosInstance, {
  get(_target, prop: string | symbol): unknown {
    return Reflect.get(_axiosRef, prop, _axiosRef)
  },
  set(_target, prop: string | symbol, value: unknown): boolean {
    return Reflect.set(_axiosRef, prop, value, _axiosRef)
  },
  apply(_target, _thisArg, args: unknown[]): unknown {
    return (_axiosRef as unknown as (...a: unknown[]) => unknown)(...args)
  },
})

// ---------------------------------------------------------------------------
// apiClient — convenience facade for non-REST capabilities
// ---------------------------------------------------------------------------

export const apiClient = {
  /** True when running inside Tauri desktop. */
  get isTauri(): boolean { return _transport.isTauri },

  /**
   * Empty string for browser/mobile; 'https://host' for Tauri.
   * Use this to build full URLs for fetch() calls that bypass Axios.
   */
  get apiOrigin(): string { return _transport.apiOrigin },

  getToken(): string { return _transport.getToken() },
  setToken(token: string): void { _transport.setToken(token) },
  clearToken(): void { _transport.clearToken() },

  /**
   * Issue a streaming (SSE) request.
   * Returns a Response whose .body is a ReadableStream of SSE lines.
   */
  stream(config: StreamConfig): Promise<Response> {
    return _transport.stream(config)
  },

  /** Trigger a file download (browser anchor or Tauri IPC binary download). */
  download(config: DownloadConfig): Promise<void> {
    return _transport.download(config)
  },

  /** Fetch plain text (for MarkdownViewer, static documents, etc.). */
  fetchText(url: string): Promise<string> {
    return _transport.fetchText(url)
  },

  /**
   * Fetch a PDF and return a Blob URL for use in <iframe src>.
   * In browser this is a passthrough; in Tauri it fetches via IPC.
   */
  fetchPdfBlobUrl(url: string): Promise<string> {
    return _transport.fetchPdfBlobUrl(url)
  },
}

// Re-export types for convenience
export type { ApiTransport, StreamConfig, DownloadConfig } from './transport/types'
export { BrowserTransport } from './transport/browser'
export { TauriTransport } from './transport/tauri'
