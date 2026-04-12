/**
 * Shared API layer — used by mobile_new/ (web browser) and as a reference for shared/api/.
 *
 * ARCHITECTURE NOTE — Two API implementations:
 * ─────────────────────────────────────────────
 * This directory (shared/api/) is used by the mobile web app (mobile_new/).
 * View/src/api/index.ts is a second, parallel implementation used by the desktop (View/)
 * and Tauri apps. It adds Tauri-specific IPC transport (tauriFetchText, tauriFetch*) and
 * localStorage session-token support that the mobile browser does not need.
 *
 * MIGRATION PATH (TODO):
 *   1. Extract the transport layer from View/src/api/index.ts into an injectable adapter
 *      interface (e.g. ApiTransport with send/stream/download methods).
 *   2. Implement two adapters: AxiosTransport (shared, for web/mobile) and TauriTransport.
 *   3. Replace View/src/api/index.ts with this shared layer + TauriTransport injected at
 *      app startup via the vite VITE_API_BASE env var.
 *   4. This will reduce the codebase by ~1 500 lines and eliminate contract-drift bugs.
 *
 * Until that migration, every API change MUST be applied in BOTH places:
 *   - shared/api/<module>.ts   (mobile web)
 *   - View/src/api/index.ts    (desktop / Tauri)
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
