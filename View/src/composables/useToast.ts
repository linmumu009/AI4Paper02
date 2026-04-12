import { ref } from 'vue'

export type ToastType = 'error' | 'warning' | 'info' | 'success'

export interface ToastMessage {
  id: number
  type: ToastType
  text: string
}

let _nextId = 1
const _toasts = ref<ToastMessage[]>([])

/**
 * Lightweight application-level toast queue.
 *
 * Usage:
 *   const { showToast } = useToast()
 *   showToast('加载失败，请稍后重试', 'error')
 *
 * Mount <AppToast /> once in App.vue to render the queue.
 */
export function useToast() {
  function showToast(text: string, type: ToastType = 'info', durationMs = 4000) {
    const id = _nextId++
    _toasts.value.push({ id, type, text })
    setTimeout(() => {
      _toasts.value = _toasts.value.filter(t => t.id !== id)
    }, durationMs)
  }

  function showError(text: string) {
    showToast(text, 'error', 5000)
  }

  function dismiss(id: number) {
    _toasts.value = _toasts.value.filter(t => t.id !== id)
  }

  return { toasts: _toasts, showToast, showError, dismiss }
}
