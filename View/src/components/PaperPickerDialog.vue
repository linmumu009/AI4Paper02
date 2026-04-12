<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchKbTree, fetchUserPaperTree } from '../api'
import type { KbTree, KbPaper, UserPaperTree } from '../types/paper'

const props = withDefaults(
  defineProps<{
    title?: string
    mode: 'research' | 'compare'
    preselectedIds?: string[]
    preselectedTitles?: Record<string, string>
  }>(),
  { preselectedIds: () => [], preselectedTitles: () => ({}) },
)

const emit = defineEmits<{
  confirm: [paperIds: string[], titles: Record<string, string>]
  cancel: []
}>()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
type ActiveTab = 'kb' | 'mypapers'
const activeTab = ref<ActiveTab>('kb')

const loadingKb = ref(false)
const loadingMy = ref(false)
const errorKb = ref('')
const errorMy = ref('')

const kbTree = ref<KbTree>({ folders: [], papers: [] })
const myTree = ref<UserPaperTree>({ folders: [], papers: [] })

const selectedIds = ref<Set<string>>(new Set())
const searchQuery = ref('')

// Collapsed folder sets per tab
const collapsedKbFolders = ref<Set<number>>(new Set())
const collapsedMyFolders = ref<Set<number>>(new Set())

// ---------------------------------------------------------------------------
// Limits
// ---------------------------------------------------------------------------
const maxSelect = computed(() => props.mode === 'research' ? 20 : 5)
const minSelect = computed(() => props.mode === 'research' ? 1 : 2)

const preselectedSet = computed(() => new Set(props.preselectedIds))

const totalSelected = computed(() => selectedIds.value.size + props.preselectedIds.length)

const canConfirm = computed(() =>
  totalSelected.value >= minSelect.value && totalSelected.value <= maxSelect.value,
)

const selectionInfo = computed(() => {
  const total = totalSelected.value
  const needed = minSelect.value - total
  if (needed > 0) return `再选 ${needed} 篇`
  if (total > maxSelect.value) return `最多 ${maxSelect.value} 篇`
  return `已选 ${total} 篇`
})

// ---------------------------------------------------------------------------
// Flat paper types
// ---------------------------------------------------------------------------
interface FlatPaper {
  paper_id: string
  title: string
  folderName: string | null
  folderId: number | null
  source: 'kb' | 'mypapers'
}

// ---------------------------------------------------------------------------
// Flatten helpers
// ---------------------------------------------------------------------------
function flattenKbTree(tree: KbTree): FlatPaper[] {
  const result: FlatPaper[] = []
  for (const p of tree.papers) {
    const title = p.paper_data?.short_title || (p.paper_data as any)?.['📖标题'] || p.paper_id
    result.push({ paper_id: p.paper_id, title, folderName: null, folderId: null, source: 'kb' })
  }
  function walkFolder(folders: any[]) {
    for (const f of folders) {
      for (const p of (f.papers || []) as KbPaper[]) {
        const title = p.paper_data?.short_title || (p.paper_data as any)?.['📖标题'] || p.paper_id
        result.push({ paper_id: p.paper_id, title, folderName: f.name, folderId: f.id, source: 'kb' })
      }
      if (f.children?.length) walkFolder(f.children)
    }
  }
  walkFolder(tree.folders)
  return result
}

function flattenMyTree(tree: UserPaperTree): FlatPaper[] {
  const result: FlatPaper[] = []
  for (const p of tree.papers) {
    result.push({ paper_id: p.paper_id, title: p.title || p.paper_id, folderName: null, folderId: null, source: 'mypapers' })
  }
  function walkFolder(folders: any[]) {
    for (const f of folders) {
      for (const p of (f.papers || [])) {
        result.push({ paper_id: p.paper_id, title: p.title || p.paper_id, folderName: f.name, folderId: f.id, source: 'mypapers' })
      }
      if (f.children?.length) walkFolder(f.children)
    }
  }
  walkFolder(tree.folders)
  return result
}

// ---------------------------------------------------------------------------
// Grouped display
// ---------------------------------------------------------------------------
interface PaperGroup {
  folderId: number | null
  folderName: string | null
  papers: FlatPaper[]
}

function groupPapers(papers: FlatPaper[]): PaperGroup[] {
  const groups: Map<string, PaperGroup> = new Map()
  for (const p of papers) {
    const key = p.folderId != null ? `folder-${p.folderId}` : 'root'
    if (!groups.has(key)) {
      groups.set(key, { folderId: p.folderId, folderName: p.folderName, papers: [] })
    }
    groups.get(key)!.papers.push(p)
  }
  // root first, then folders sorted by name
  const arr = [...groups.values()]
  return arr.sort((a, b) => {
    if (a.folderId == null) return -1
    if (b.folderId == null) return 1
    return (a.folderName ?? '').localeCompare(b.folderName ?? '')
  })
}

const filteredKbPapers = computed(() => {
  const flat = flattenKbTree(kbTree.value)
  if (!searchQuery.value.trim()) return flat
  const q = searchQuery.value.toLowerCase()
  return flat.filter(p => p.title.toLowerCase().includes(q))
})

const filteredMyPapers = computed(() => {
  const flat = flattenMyTree(myTree.value)
  if (!searchQuery.value.trim()) return flat
  const q = searchQuery.value.toLowerCase()
  return flat.filter(p => p.title.toLowerCase().includes(q))
})

const currentGroups = computed(() => {
  const papers = activeTab.value === 'kb' ? filteredKbPapers.value : filteredMyPapers.value
  return groupPapers(papers)
})

const currentLoading = computed(() => activeTab.value === 'kb' ? loadingKb.value : loadingMy.value)
const currentError = computed(() => activeTab.value === 'kb' ? errorKb.value : errorMy.value)
const currentEmpty = computed(() =>
  !currentLoading.value && !currentError.value &&
  (activeTab.value === 'kb' ? filteredKbPapers.value.length === 0 : filteredMyPapers.value.length === 0),
)

// ---------------------------------------------------------------------------
// Folder collapse
// ---------------------------------------------------------------------------
function isFolderCollapsed(folderId: number | null): boolean {
  if (folderId == null) return false
  const set = activeTab.value === 'kb' ? collapsedKbFolders.value : collapsedMyFolders.value
  return set.has(folderId)
}

function toggleFolder(folderId: number | null) {
  if (folderId == null) return
  const set = activeTab.value === 'kb' ? collapsedKbFolders.value : collapsedMyFolders.value
  const next = new Set(set)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  if (activeTab.value === 'kb') collapsedKbFolders.value = next
  else collapsedMyFolders.value = next
}

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------
function togglePaper(paperId: string) {
  if (preselectedSet.value.has(paperId)) return
  const next = new Set(selectedIds.value)
  if (next.has(paperId)) {
    next.delete(paperId)
  } else {
    if (totalSelected.value >= maxSelect.value) return
    next.add(paperId)
  }
  selectedIds.value = next
}

// ---------------------------------------------------------------------------
// Confirm
// ---------------------------------------------------------------------------
function confirm() {
  if (!canConfirm.value) return
  const allIds = [...props.preselectedIds, ...selectedIds.value]
  const allTitles: Record<string, string> = { ...props.preselectedTitles }
  for (const p of filteredKbPapers.value) {
    if (selectedIds.value.has(p.paper_id)) allTitles[p.paper_id] = p.title
  }
  for (const p of filteredMyPapers.value) {
    if (selectedIds.value.has(p.paper_id)) allTitles[p.paper_id] = p.title
  }
  emit('confirm', allIds, allTitles)
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------
onMounted(async () => {
  loadingKb.value = true
  errorKb.value = ''
  try {
    kbTree.value = await fetchKbTree('kb')
  } catch {
    errorKb.value = '加载知识库失败，请重试'
  } finally {
    loadingKb.value = false
  }

  loadingMy.value = true
  errorMy.value = ''
  try {
    myTree.value = await fetchUserPaperTree()
  } catch {
    errorMy.value = '加载我的论文失败，请重试'
  } finally {
    loadingMy.value = false
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center p-4"
      @click.self="emit('cancel')"
    >
      <div class="w-full max-w-2xl max-h-[85vh] bg-bg-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">

        <!-- ===== Header ===== -->
        <div class="px-5 pt-4 pb-3 border-b border-border shrink-0">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2.5">
              <div class="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
                :class="mode === 'research' ? 'bg-accent-primary/10 border border-accent-primary/20' : 'bg-purple-400/10 border border-purple-400/20'"
              >
                <svg v-if="mode === 'research'" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                  class="text-accent-primary">
                  <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                  <path d="M11 8v6"/><path d="M8 11h6"/>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                  class="text-purple-400">
                  <path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/>
                  <path d="M15 15 3 3"/>
                </svg>
              </div>
              <div>
                <h3 class="text-sm font-bold text-text-primary leading-tight">
                  {{ mode === 'research' ? '深度研究' : '对比分析' }}
                </h3>
                <p class="text-[11px] text-text-muted leading-tight mt-0.5">
                  {{ mode === 'research' ? '选择 1–20 篇论文' : '选择 2–5 篇论文' }}
                </p>
              </div>
            </div>
            <button
              class="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-hover border-none bg-transparent cursor-pointer transition-colors"
              @click="emit('cancel')"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="w-4 h-4">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- Tab bar -->
          <div class="flex items-center gap-1 p-0.5 bg-bg-elevated rounded-xl border border-border">
            <button
              class="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer border-none"
              :class="activeTab === 'kb'
                ? 'bg-bg-card text-text-primary shadow-sm'
                : 'bg-transparent text-text-muted hover:text-text-primary'"
              @click="activeTab = 'kb'"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
              </svg>
              知识库
              <span v-if="!loadingKb" class="tabular-nums text-[10px] opacity-60">
                {{ flattenKbTree(kbTree).length }}
              </span>
            </button>
            <button
              class="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer border-none"
              :class="activeTab === 'mypapers'
                ? 'bg-bg-card text-text-primary shadow-sm'
                : 'bg-transparent text-text-muted hover:text-text-primary'"
              @click="activeTab = 'mypapers'"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
              </svg>
              我的论文
              <span v-if="!loadingMy" class="tabular-nums text-[10px] opacity-60">
                {{ flattenMyTree(myTree).length }}
              </span>
            </button>
          </div>

          <!-- Search -->
          <div class="mt-2.5 relative">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索论文标题…"
              class="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-border bg-bg-elevated text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary/20 focus:border-accent-primary/40 transition-all"
            />
            <button
              v-if="searchQuery"
              class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center rounded text-text-muted hover:text-text-primary border-none bg-transparent cursor-pointer transition-colors"
              @click="searchQuery = ''"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="w-3 h-3">
                <path d="M18 6 6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- ===== Preselected pills ===== -->
        <div
          v-if="preselectedIds.length > 0"
          class="px-5 py-2.5 border-b border-border bg-bg-elevated/50 shrink-0"
        >
          <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5">已关联（固定）</p>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="pid in preselectedIds"
              :key="pid"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-tinder-blue/12 text-tinder-blue border border-tinder-blue/20"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="w-2.5 h-2.5 shrink-0">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ preselectedTitles[pid] || pid }}
            </span>
          </div>
        </div>

        <!-- ===== Paper list ===== -->
        <div class="flex-1 overflow-y-auto min-h-0">
          <!-- Loading -->
          <div v-if="currentLoading" class="flex flex-col items-center justify-center py-16 gap-3">
            <svg class="animate-spin h-6 w-6 text-accent-primary" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <span class="text-xs text-text-muted">加载中…</span>
          </div>

          <!-- Error -->
          <div v-else-if="currentError" class="flex flex-col items-center justify-center py-16 gap-2">
            <svg class="w-8 h-8 text-red-400/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>
            </svg>
            <p class="text-sm text-red-400">{{ currentError }}</p>
          </div>

          <!-- Empty -->
          <div v-else-if="currentEmpty" class="flex flex-col items-center justify-center py-16 gap-2 text-text-muted">
            <svg class="w-10 h-10 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
            </svg>
            <p class="text-sm font-medium">
              {{ searchQuery ? '无匹配论文' : (activeTab === 'kb' ? '知识库暂无论文' : '尚未上传论文') }}
            </p>
            <p class="text-xs opacity-70">
              {{ searchQuery ? '尝试其他关键词' : (activeTab === 'kb' ? '请先从侧栏添加论文到知识库' : '请先上传论文到我的论文库') }}
            </p>
          </div>

          <!-- Grouped paper list -->
          <div v-else class="px-3 py-3 space-y-3">
            <div
              v-for="group in currentGroups"
              :key="group.folderId != null ? `folder-${group.folderId}` : 'root'"
            >
              <!-- Folder header (only for folders, not root) -->
              <button
                v-if="group.folderName"
                class="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors hover:bg-bg-elevated cursor-pointer border-none bg-transparent mb-1"
                @click="toggleFolder(group.folderId)"
              >
                <svg
                  class="w-3.5 h-3.5 text-text-muted transition-transform shrink-0"
                  :class="isFolderCollapsed(group.folderId) ? '-rotate-90' : ''"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                >
                  <path d="m6 9 6 6 6-6"/>
                </svg>
                <svg class="w-3.5 h-3.5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/>
                </svg>
                <span class="text-xs font-semibold text-text-secondary flex-1 truncate">{{ group.folderName }}</span>
                <span class="text-[10px] text-text-muted tabular-nums">{{ group.papers.length }}</span>
              </button>

              <!-- Root section label -->
              <div v-else-if="currentGroups.length > 1" class="flex items-center gap-2 px-2 py-1 mb-1">
                <span class="text-[10px] font-semibold text-text-muted uppercase tracking-wider">未归档</span>
                <span class="text-[10px] text-text-muted tabular-nums">{{ group.papers.length }}</span>
              </div>

              <!-- Papers in this group -->
              <div
                v-if="!isFolderCollapsed(group.folderId)"
                class="space-y-0.5"
                :class="group.folderName ? 'ml-4' : ''"
              >
                <button
                  v-for="paper in group.papers"
                  :key="paper.paper_id"
                  class="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs transition-all cursor-pointer border group relative overflow-hidden"
                  :class="[
                    preselectedSet.has(paper.paper_id)
                      ? 'border-tinder-blue/25 bg-tinder-blue/6 text-tinder-blue/80 cursor-default'
                      : selectedIds.has(paper.paper_id)
                        ? (mode === 'research'
                            ? 'border-accent-primary/30 bg-accent-primary/8 text-text-primary'
                            : 'border-purple-400/30 bg-purple-400/8 text-text-primary')
                        : 'border-transparent bg-bg-elevated/40 hover:bg-bg-elevated hover:border-border text-text-secondary',
                  ]"
                  :disabled="preselectedSet.has(paper.paper_id)"
                  @click="togglePaper(paper.paper_id)"
                >
                  <!-- Left accent bar for selected -->
                  <div
                    v-if="selectedIds.has(paper.paper_id) && !preselectedSet.has(paper.paper_id)"
                    class="absolute left-0 top-0 bottom-0 w-0.5 rounded-l-xl"
                    :class="mode === 'research' ? 'bg-accent-primary' : 'bg-purple-400'"
                  />

                  <!-- Checkbox -->
                  <span
                    class="shrink-0 w-4 h-4 rounded-md flex items-center justify-center border transition-all"
                    :class="[
                      preselectedSet.has(paper.paper_id)
                        ? 'border-tinder-blue bg-tinder-blue/20'
                        : selectedIds.has(paper.paper_id)
                          ? (mode === 'research' ? 'border-accent-primary bg-accent-primary' : 'border-purple-400 bg-purple-400')
                          : 'border-border bg-bg-elevated group-hover:border-text-muted',
                    ]"
                  >
                    <svg
                      v-if="preselectedSet.has(paper.paper_id) || selectedIds.has(paper.paper_id)"
                      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" class="w-2.5 h-2.5"
                      :class="preselectedSet.has(paper.paper_id) ? 'text-tinder-blue' : 'text-white'"
                    >
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </span>

                  <!-- Title -->
                  <span class="flex-1 min-w-0 font-medium leading-snug truncate group-hover:text-text-primary transition-colors">
                    {{ paper.title }}
                  </span>

                  <!-- Source badge (only shown when mixed context) -->
                  <span
                    v-if="preselectedSet.has(paper.paper_id)"
                    class="shrink-0 text-[10px] text-tinder-blue/60 font-medium"
                  >固定</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== Footer ===== -->
        <div class="px-5 py-3 border-t border-border flex items-center justify-between gap-3 shrink-0 bg-bg-elevated/30">
          <!-- Selection progress -->
          <div class="flex items-center gap-2.5 min-w-0">
            <!-- Progress dots for compare mode (small count) -->
            <div v-if="mode === 'compare'" class="flex items-center gap-1">
              <span
                v-for="i in maxSelect"
                :key="i"
                class="w-2 h-2 rounded-full transition-all"
                :class="i <= totalSelected
                  ? 'bg-purple-400'
                  : 'bg-border'"
              />
            </div>
            <span class="text-xs font-semibold truncate" :class="canConfirm ? 'text-text-muted' : 'text-tinder-pink'">
              {{ selectionInfo }}
            </span>
          </div>

          <div class="flex items-center gap-2 shrink-0">
            <button
              class="px-4 py-1.5 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover hover:text-text-primary transition-all"
              @click="emit('cancel')"
            >
              取消
            </button>
            <button
              :disabled="!canConfirm"
              class="px-5 py-1.5 rounded-full text-xs font-semibold border-none cursor-pointer transition-all"
              :class="canConfirm
                ? mode === 'research'
                  ? 'text-white bg-gradient-to-r from-[#0ea5e9] to-[#6366f1] hover:opacity-90 active:scale-95'
                  : 'text-white bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:opacity-90 active:scale-95'
                : 'text-text-muted bg-bg-hover cursor-not-allowed opacity-50'"
              @click="confirm"
            >
              {{ mode === 'research' ? '开始深研' : '开始对比' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
