/**
 * 统一的"打开外部链接"工具函数。
 *
 * - Tauri 桌面端：调用 tauri-plugin-opener 在系统默认浏览器中打开，
 *   避免 WebView2 可能把外部链接在 WebView 内导航的问题。
 * - Web 浏览器：使用 window.open，行为与原来一致。
 */

const _tauriInvoke: ((cmd: string, args?: Record<string, unknown>) => Promise<unknown>) | null =
  (window as any).__TAURI_INTERNALS__?.invoke ?? null

/**
 * 在系统默认浏览器（或对应的默认应用）中打开给定 URL。
 * 对于 Tauri 桌面端，走 opener 插件；对于网页端，走 window.open。
 */
export function openExternal(url: string): void {
  if (_tauriInvoke) {
    _tauriInvoke('plugin:opener|open_url', { url }).catch(() => {
      // opener 插件不可用时降级
      window.open(url, '_blank', 'noopener,noreferrer')
    })
  } else {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
