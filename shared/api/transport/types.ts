/**
 * ApiTransport — the contract that every environment adapter must satisfy.
 *
 * Implementations:
 *   BrowserTransport  (shared/api/transport/browser.ts) — web browser & mobile PWA
 *   TauriTransport    (shared/api/transport/tauri.ts)   — Tauri desktop app (IPC path)
 *
 * Domain API modules (shared/api/*.ts) only import from `shared/api/client`; they
 * never import from a concrete transport.  The active transport is swapped in at
 * application startup via configureTransport().
 */

import type { AxiosInstance } from 'axios'

// ---------------------------------------------------------------------------
// Request/stream/download config types
// ---------------------------------------------------------------------------

export interface StreamConfig {
  /** HTTP method — typically 'POST'. */
  method: string
  /**
   * API endpoint path, WITHOUT the leading '/api' prefix.
   * e.g. '/papers/2501.00001/chat', '/idea/candidates/generate'
   * The transport adds the full origin + /api prefix automatically.
   */
  path: string
  /** Request body. Objects are JSON.stringify'd; strings are sent as-is. */
  body?: unknown
  signal?: AbortSignal
}

export interface DownloadConfig {
  /**
   * API endpoint path + query string, WITHOUT the leading '/api' prefix.
   * e.g. '/download/paper-file?paper_id=…&file_type=pdf'
   */
  path: string
  /** Used as the filename when the server does not return Content-Disposition. */
  fallbackName: string
  /** HTTP method — default 'GET'. */
  method?: string
  /** Request body for POST downloads. */
  body?: unknown
}

// ---------------------------------------------------------------------------
// ApiTransport interface
// ---------------------------------------------------------------------------

export interface ApiTransport {
  /** True only inside the Tauri desktop shell. */
  readonly isTauri: boolean

  /**
   * Empty string for browser / mobile.
   * 'https://your-server.com' (no trailing slash) for Tauri.
   */
  readonly apiOrigin: string

  /** An Axios instance pre-configured for this environment. */
  readonly axiosInstance: AxiosInstance

  // ---- Session token --------------------------------------------------
  /** Returns the current session token (empty string when absent). */
  getToken(): string
  /** Persists the session token (localStorage on desktop, noop on browser). */
  setToken(token: string): void
  /** Removes the session token. */
  clearToken(): void

  // ---- Streaming -------------------------------------------------------
  /**
   * Issues a streaming HTTP request and returns a Response whose body is a
   * ReadableStream of SSE lines.
   * Both Browser (native fetch) and Tauri (Rust Channel) implement this.
   */
  stream(config: StreamConfig): Promise<Response>

  // ---- Downloads -------------------------------------------------------
  /**
   * Fetches a file from the API and triggers a browser "Save As" dialog.
   * Browser: fetch + Blob + <a> click.
   * Tauri: Rust direct_download_binary + Blob URL.
   */
  download(config: DownloadConfig): Promise<void>

  // ---- Utility ---------------------------------------------------------
  /**
   * Fetches a text/markdown resource and returns its content as a string.
   * Needed because WebView2 cannot fetch cross-origin URLs via the DOM.
   */
  fetchText(url: string): Promise<string>

  /**
   * Downloads a PDF and returns a Blob URL suitable for use in an <iframe>.
   * Browser: returns the original URL unchanged.
   * Tauri: downloads via Rust IPC and returns URL.createObjectURL(blob).
   */
  fetchPdfBlobUrl(url: string): Promise<string>
}
