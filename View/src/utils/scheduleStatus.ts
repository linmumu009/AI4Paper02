export type ScheduleStatusTone = 'success' | 'warning' | 'neutral' | 'error'

export interface ScheduleHistoryLike {
  success: boolean
  exit_code: number | null
  user_count: number
  arxiv_count?: number | null
  outcome?: 'completed' | 'no_new_papers' | 'source_empty_retry' | 'failed'
}

export interface PipelineRuntimeStatusLike {
  running: boolean
  exit_code: number | null
}

export function getPipelineRuntimeStatus(
  record: PipelineRuntimeStatusLike | null | undefined,
): { label: string; tone: ScheduleStatusTone } {
  if (!record) return { label: '未知', tone: 'neutral' }
  if (record.running) return { label: '运行中', tone: 'neutral' }
  if (record.exit_code === 0) return { label: '已完成', tone: 'success' }
  if (record.exit_code === 4) return { label: '等待自动重试', tone: 'warning' }
  if (record.exit_code !== null) return { label: '异常退出', tone: 'error' }
  return { label: '空闲', tone: 'neutral' }
}

export function getScheduleStatus(record: ScheduleHistoryLike): {
  label: string
  tone: ScheduleStatusTone
} {
  if (record.outcome === 'source_empty_retry' || record.exit_code === 4) {
    return { label: '等待重试', tone: 'warning' }
  }
  if (
    record.outcome === 'no_new_papers'
    || (record.success && record.arxiv_count === 0)
    || (record.success && record.arxiv_count == null && record.user_count === 0)
  ) {
    return { label: '无新论文', tone: 'neutral' }
  }
  if (record.success) return { label: '成功', tone: 'success' }
  return { label: `失败 (${record.exit_code ?? '?'})`, tone: 'error' }
}

export function formatChinaTimestamp(value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return fallback
  const values = Object.fromEntries(
    new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(parsed).map(part => [part.type, part.value]),
  )
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`
}

export function formatScheduleDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): string {
  if (!startedAt || !finishedAt) return '—'
  const elapsedSeconds = Math.max(
    0,
    (new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000,
  )
  if (!Number.isFinite(elapsedSeconds)) return '—'
  if (elapsedSeconds < 60) return `${Math.max(1, Math.round(elapsedSeconds))} 秒`
  if (elapsedSeconds < 3600) return `${Math.round(elapsedSeconds / 60)} 分钟`
  const hours = Math.floor(elapsedSeconds / 3600)
  const minutes = Math.round((elapsedSeconds % 3600) / 60)
  return minutes > 0 ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`
}

export function formatScheduleClock(hour: number | undefined, minute: number | undefined): string {
  const safeHour = Number.isInteger(hour) ? Math.min(23, Math.max(0, hour as number)) : 0
  const safeMinute = Number.isInteger(minute) ? Math.min(59, Math.max(0, minute as number)) : 0
  return `${String(safeHour).padStart(2, '0')}:${String(safeMinute).padStart(2, '0')}`
}
