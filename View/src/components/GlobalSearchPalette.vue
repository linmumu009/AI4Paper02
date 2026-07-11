<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchGlobalSearch, type GlobalSearchResult } from '../api/globalSearch'
import { useGlobalSearch } from '../composables/useGlobalSearch'
import { useGlobalChat } from '../composables/useGlobalChat'
import { isAuthenticated } from '../stores/auth'
import { getRecentPapers } from '../utils/recentPapers'

interface PaletteItem {
  key: string
  type: string
  title: string
  subtitle: string
  route?: string
  action?: 'chat'
}

const router = useRouter()
const globalChat = useGlobalChat()
const { isOpen, close } = useGlobalSearch()

const inputRef = ref<HTMLInputElement | null>(null)
const query = ref('')
const remoteResults = ref<GlobalSearchResult[]>([])
const recentItems = ref<PaletteItem[]>([])
const loading = ref(false)
const error = ref('')
const selectedIndex = ref(0)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let requestSerial = 0

const quickItems: PaletteItem[] = [
  { key: 'quick-knowledge', type: '入口', title: '知识库', subtitle: '收藏论文、笔记与文件', route: '/?tool=knowledge' },
  { key: 'quick-compare', type: '入口', title: '对比库', subtitle: '已保存的论文对比报告', route: '/?tool=compare-library' },
  { key: 'quick-research', type: '入口', title: '研究库', subtitle: '课题空间与深度研究', route: '/projects' },
  { key: 'quick-mypapers', type: '入口', title: '我的论文', subtitle: '上传或导入的文献', route: '/?tab=mypapers' },
  { key: 'quick-chat', type: 'AI 工具', title: 'AI 对话', subtitle: '打开全局问答助手', action: 'chat' },
  { key: 'quick-workbench', type: 'AI 工具', title: '灵感工作台', subtitle: '生成研究提案', route: '/workbench' },
  { key: 'quick-tasks', type: '入口', title: '任务中心', subtitle: '查看后台任务进度', route: '/profile?tab=task_center' },
]

const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase('zh-CN'))

const matchingQuickItems = computed(() => {
  const q = normalizedQuery.value
  if (!q) return quickItems
  return quickItems.filter(item => `${item.title} ${item.subtitle}`.toLocaleLowerCase('zh-CN').includes(q))
})

const resultItems = computed<PaletteItem[]>(() => {
  if (!normalizedQuery.value) {
    return [...recentItems.value, ...quickItems]
  }
  return [
    ...remoteResults.value.map(item => ({
      key: `${item.type}-${item.id}`,
      type: typeLabel(item.type),
      title: item.title,
      subtitle: item.subtitle,
      route: item.route,
    })),
    ...matchingQuickItems.value,
  ]
})

function typeLabel(type: GlobalSearchResult['type']): string {
  const labels: Record<GlobalSearchResult['type'], string> = {
    paper: '论文',
    note: '笔记',
    compare: '对比',
    research: '研究',
    project: '课题',
    user_paper: '我的论文',
  }
  return labels[type]
}

function loadRecentItems() {
  recentItems.value = getRecentPapers(6).map(item => ({
    key: `recent-${item.source}-${item.paperId}`,
    type: '最近阅读',
    title: item.title,
    subtitle: item.firstAuthor || item.paperId,
    route: item.source === 'user'
      ? `/?tab=mypapers&paper=${encodeURIComponent(item.paperId)}`
      : `/papers/${encodeURIComponent(item.paperId)}`,
  }))
}

async function runSearch(value: string) {
  const serial = ++requestSerial
  if (!value || !isAuthenticated.value) {
    remoteResults.value = []
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const response = await fetchGlobalSearch(value, 30)
    if (serial === requestSerial) remoteResults.value = response.results
  } catch {
    if (serial === requestSerial) {
      remoteResults.value = []
      error.value = '搜索暂时不可用，请稍后重试'
    }
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

watch(query, (value) => {
  selectedIndex.value = 0
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { void runSearch(value.trim()) }, 220)
})

watch(isOpen, async (open) => {
  if (!open) return
  query.value = ''
  remoteResults.value = []
  error.value = ''
  selectedIndex.value = 0
  loadRecentItems()
  await nextTick()
  inputRef.value?.focus()
})

function moveSelection(delta: number) {
  const count = resultItems.value.length
  if (!count) return
  selectedIndex.value = (selectedIndex.value + delta + count) % count
}

async function activate(item: PaletteItem | undefined) {
  if (!item) return
  close()
  if (item.action === 'chat') {
    globalChat.open()
    return
  }
  if (item.route) await router.push(item.route)
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveSelection(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveSelection(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    void activate(resultItems.value[selectedIndex.value])
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

function onGlobalKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
    event.preventDefault()
    isOpen.value = true
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="isOpen"
        class="fixed inset-0 z-[120] flex items-start justify-center bg-black/65 px-3 pt-[10vh] backdrop-blur-sm"
        @mousedown.self="close"
      >
        <section
          class="flex max-h-[72vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-bg-card shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="global-search-title"
        >
          <h2 id="global-search-title" class="sr-only">搜索研究资产</h2>
          <div class="flex items-center gap-3 border-b border-border px-4 py-3">
            <svg aria-hidden="true" class="h-5 w-5 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
            <input
              ref="inputRef"
              v-model="query"
              class="min-w-0 flex-1 border-none bg-transparent text-base text-text-primary outline-none placeholder:text-text-muted"
              type="search"
              autocomplete="off"
              placeholder="搜索论文、笔记、对比报告和研究会话…"
              aria-label="搜索研究资产"
              aria-controls="global-search-results"
              :aria-activedescendant="resultItems[selectedIndex] ? `global-search-item-${selectedIndex}` : undefined"
              @keydown="onInputKeydown"
            />
            <span v-if="loading" class="text-xs text-text-muted" role="status">搜索中…</span>
            <kbd class="hidden rounded border border-border bg-bg-elevated px-1.5 py-0.5 text-[10px] text-text-muted sm:inline">Esc</kbd>
          </div>

          <div v-if="!isAuthenticated" class="border-b border-border/60 px-4 py-2 text-xs text-text-muted">
            登录后可搜索知识库、笔记、对比报告和研究会话；当前仍可使用快捷入口和最近阅读。
          </div>

          <div id="global-search-results" class="min-h-0 flex-1 overflow-y-auto p-2" role="listbox">
            <p v-if="error" class="px-3 py-6 text-center text-sm text-tinder-pink" role="alert">{{ error }}</p>
            <p
              v-else-if="normalizedQuery && !loading && resultItems.length === 0"
              class="px-3 py-8 text-center text-sm text-text-muted"
            >
              没有找到相关研究资产
            </p>
            <template v-else>
              <p class="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-widest text-text-muted">
                {{ normalizedQuery ? '搜索结果' : (recentItems.length ? '最近访问与快捷入口' : '快捷入口') }}
              </p>
              <button
                v-for="(item, index) in resultItems"
                :id="`global-search-item-${index}`"
                :key="item.key"
                type="button"
                class="flex w-full items-center gap-3 rounded-xl border-none px-3 py-2.5 text-left transition-colors"
                :class="index === selectedIndex ? 'bg-bg-hover' : 'bg-transparent hover:bg-bg-hover/70'"
                role="option"
                :aria-selected="index === selectedIndex"
                @mouseenter="selectedIndex = index"
                @click="activate(item)"
              >
                <span class="w-16 shrink-0 rounded-full bg-bg-elevated px-2 py-1 text-center text-[10px] font-medium text-text-secondary">
                  {{ item.type }}
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm font-medium text-text-primary">{{ item.title }}</span>
                  <span class="mt-0.5 block truncate text-xs text-text-muted">{{ item.subtitle }}</span>
                </span>
                <span aria-hidden="true" class="text-text-muted/60">↵</span>
              </button>
            </template>
          </div>

          <div class="hidden items-center gap-4 border-t border-border px-4 py-2 text-[10px] text-text-muted sm:flex">
            <span>↑↓ 选择</span><span>Enter 打开</span><span>Ctrl/⌘ K 随时搜索</span>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
