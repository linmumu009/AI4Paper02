import { onBeforeUnmount, onMounted, readonly, ref } from 'vue'

export type PollingCallback = () => boolean | void | Promise<boolean | void>

export interface PollingTaskOptions {
  intervalMs: number
  immediate?: boolean
  pauseWhenHidden?: boolean
}

export function createPollingTask(callback: PollingCallback, options: PollingTaskOptions) {
  const active = ref(false)
  const running = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  function clearTimer() {
    if (timer) clearTimeout(timer)
    timer = null
  }

  function isHidden() {
    return options.pauseWhenHidden !== false
      && typeof document !== 'undefined'
      && document.hidden
  }

  function schedule(delay = options.intervalMs) {
    clearTimer()
    if (!active.value || isHidden()) return
    timer = setTimeout(run, Math.max(0, delay))
  }

  async function run() {
    timer = null
    if (!active.value || running.value || isHidden()) return

    running.value = true
    try {
      const shouldContinue = await callback()
      if (shouldContinue === false) {
        stop()
        return
      }
    } finally {
      running.value = false
    }

    if (active.value) schedule()
  }

  function start(immediate = options.immediate === true) {
    if (active.value) return
    active.value = true
    schedule(immediate ? 0 : options.intervalMs)
  }

  function stop() {
    active.value = false
    clearTimer()
  }

  function handleVisibilityChange() {
    if (!active.value) return
    if (isHidden()) clearTimer()
    else schedule(0)
  }

  return {
    active: readonly(active),
    running: readonly(running),
    start,
    stop,
    runNow: () => schedule(0),
    handleVisibilityChange,
  }
}

export function usePollingTask(callback: PollingCallback, options: PollingTaskOptions) {
  const task = createPollingTask(callback, options)

  onMounted(() => {
    if (options.pauseWhenHidden !== false) {
      document.addEventListener('visibilitychange', task.handleVisibilityChange)
    }
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', task.handleVisibilityChange)
    task.stop()
  })

  return task
}
