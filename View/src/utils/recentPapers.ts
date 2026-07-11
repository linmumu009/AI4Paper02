/**
 * recentPapers.ts
 *
 * 桌面端专属：维护一份最近阅读的论文列表，存储于 localStorage。
 * - 仅记录轻量元数据，不存储全文，避免占用过多存储空间。
 * - 最多保留 MAX_ITEMS 条，最新的排在最前面。
 * - 网页端也可使用此工具，但主要面向桌面端"回到上次阅读"场景。
 */

export interface RecentPaperEntry {
  /** arXiv 论文 ID 或用户论文 ID */
  paperId: string
  /** 显示标题 */
  title: string
  /** 首作者 */
  firstAuthor?: string
  /** 来源：'arxiv' | 'user' | 'kb' */
  source: 'arxiv' | 'user' | 'kb'
  /** 最后访问时间戳（ms） */
  visitedAt: number
}

const STORAGE_KEY = 'ai4papers_recent_papers'
const MAX_ITEMS = 50

function loadList(): RecentPaperEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as RecentPaperEntry[]
  } catch {
    return []
  }
}

function saveList(list: RecentPaperEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // localStorage 配额满时静默失败
  }
}

/**
 * 记录一次论文访问（如已存在则移到最前并更新时间）。
 */
export function recordPaperVisit(entry: Omit<RecentPaperEntry, 'visitedAt'>): void {
  const list = loadList().filter(e => e.paperId !== entry.paperId)
  list.unshift({ ...entry, visitedAt: Date.now() })
  saveList(list.slice(0, MAX_ITEMS))
}

/**
 * 获取最近阅读列表（最新优先）。
 */
export function getRecentPapers(limit = 10): RecentPaperEntry[] {
  return loadList().slice(0, limit)
}

/**
 * 清空最近阅读记录。
 */
export function clearRecentPapers(): void {
  localStorage.removeItem(STORAGE_KEY)
}
