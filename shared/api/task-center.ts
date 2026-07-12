import { http } from './http'
import type {
  TaskCenterListResponse,
  TaskCenterSummary,
  TaskActionResponse,
  TaskKind,
  TaskStatus,
} from '../types/task-center'

export interface FetchTasksParams {
  status?: TaskStatus | 'active'
  kind?: TaskKind
  limit?: number
  include_completed?: boolean
}

export async function fetchTasks(params?: FetchTasksParams): Promise<TaskCenterListResponse> {
  const { data } = await http.get<TaskCenterListResponse>('/tasks', { params })
  return data
}

export async function fetchTaskSummary(): Promise<TaskCenterSummary> {
  const { data } = await http.get<TaskCenterSummary>('/tasks/summary')
  return data
}

export async function retryTask(taskId: string): Promise<TaskActionResponse> {
  const { data } = await http.post<TaskActionResponse>(`/tasks/${encodeURIComponent(taskId)}/retry`)
  return data
}

export async function cancelTask(taskId: string): Promise<TaskActionResponse> {
  const { data } = await http.post<TaskActionResponse>(`/tasks/${encodeURIComponent(taskId)}/cancel`)
  return data
}

export async function continueTask(taskId: string): Promise<TaskActionResponse> {
  const { data } = await http.post<TaskActionResponse>(`/tasks/${encodeURIComponent(taskId)}/continue`)
  return data
}

export function taskKindLabel(kind: TaskKind): string {
  const labels: Record<TaskKind, string> = {
    kb_process: 'KB 解析',
    kb_translate: 'KB 翻译',
    kb_classify: 'KB 分类',
    user_paper_process: '论文解析',
    user_paper_translate: '论文翻译',
    pipeline_run: 'Pipeline',
    deep_research: '深度研究',
    paper_compare: '论文对比',
  }
  return labels[kind] ?? kind
}

export function taskStatusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    pending: '等待中',
    running: '处理中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    skipped: '已跳过',
    none: '未开始',
  }
  return labels[status] ?? status
}

export function isActiveTask(status: TaskStatus): boolean {
  return status === 'pending' || status === 'running'
}
