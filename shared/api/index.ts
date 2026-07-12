/**
 * Shared API layer — used by all frontends: mobile_new/, View/ (desktop/Tauri), and web browser.
 *
 * ARCHITECTURE
 * ─────────────────────────────────────────────
 * All HTTP traffic goes through the active ApiTransport (see shared/api/client.ts).
 *
 *   BrowserTransport (default)
 *     - Axios with withCredentials: true, baseURL: '/api'
 *     - SSE streaming via browser fetch()
 *     - Downloads via fetch + Blob + <a> click
 *     - Session: httpOnly cookie managed by the server
 *
 *   TauriTransport (desktop app, configured at startup in View/src/api/index.ts)
 *     - Axios with custom adapter → Rust direct_request / direct_upload
 *     - SSE streaming via Rust Channel (direct_request_stream)
 *     - Downloads via Rust direct_download_binary
 *     - Session: localStorage 'ai4papers_session_id' Bearer header
 *
 * To configure at app startup:
 *   import { configureTransport, TauriTransport } from '@shared/api/client'
 *   configureTransport(new TauriTransport(import.meta.env.VITE_API_BASE))
 *
 * The `http` export is a Proxy — always delegates to the current transport's
 * Axios instance.  Domain modules import `http` from './http' and continue to
 * work after configureTransport() is called, without re-import.
 */

// HTTP client
export { http } from './http'

// Authentication & subscription & admin users
export * from './auth'

// Papers, dates, digest, pipeline status
export * from './papers'

// Knowledge base (folders, papers, notes, annotations, compare results)
export * from './kb'

// KB paper processing & translation
export * from './kb-processing'

// Paper chat & general chat
export * from './chat'

// Engagement (sign-in, tasks, rewards, streak)
export * from './engagement'

// Entitlements
export * from './entitlement'

// Analytics event reporting
export * from './analytics'

// Idea generation v2
export * from './idea'

// Deep research sessions
export * from './research'

// Research projects / topic spaces
export * from './projects'

// User-uploaded papers
export * from './user-papers'

// Community
export * from './community'

// Announcements
export * from './announcements'

// Admin (pipeline, schedule, system config, llm/prompt configs, presets, analytics)
export * from './admin'

// Download utilities (browser-native, no Tauri IPC)
export * from './download'

// Preference learning closed loop
export * from './preference'

// Weekly recap & spaced review cards
export * from './recap'

// Research radar daily summary
export * from './radar'

// Task center unified task view
export * from './task-center'
