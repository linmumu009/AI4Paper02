<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import { fetchResearchSessions, saveResearchSession, deleteResearchSession } from '@shared/api'
import type { ResearchSession } from '@shared/types/research'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'ResearchLibraryView' })

const router = useRouter()

const sessions = ref<ResearchSession[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')

const menuVisible = ref(false)
const menuTarget = ref<ResearchSession | null>(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await fetchResearchSessions(100, true)
    sessions.value = result.sessions
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filteredSessions = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter((s) => s.question.toLowerCase().includes(q))
})

function openSession(session: ResearchSession) {
  router.push({ path: '/research', query: { session_id: String(session.id) } })
}

function openMenu(session: ResearchSession) {
  menuTarget.value = session
  menuVisible.value = true
}

async function doUnsave() {
  if (!menuTarget.value) return
  menuVisible.value = false
  const session = menuTarget.value
  try {
    await saveResearchSession(session.id, false)
    sessions.value = sessions.value.filter((s) => s.id !== session.id)
    showToast('已从研究库移除')
  } catch {
    showToast('操作失败')
  }
}

async function doDelete() {
  if (!menuTarget.value) return
  menuVisible.value = false
  const session = menuTarget.value
  try {
    await showDialog({
      title: '删除研究',
      message: '确定删除此研究会话？',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteResearchSession(session.id)
    sessions.value = sessions.value.filter((s) => s.id !== session.id)
    showToast('已删除')
  } catch {
    // user cancelled
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function statusLabel(status: ResearchSession['status']) {
  if (status === 'done') return '完成'
  if (status === 'running') return '进行中'
  if (status === 'error') return '失败'
  return '等待中'
}

function statusColor(status: ResearchSession['status']) {
  if (status === 'done') return 'text-tinder-green'
  if (status === 'running') return 'text-tinder-blue'
  if (status === 'error') return 'text-tinder-pink'
  return 'text-text-muted'
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="研究库" :show-back="false">
      <template #right>
        <button
          type="button"
          class="w-10 h-10 flex items-center justify-center text-text-secondary"
          aria-label="新建研究"
          @click="router.push('/research')"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <!-- Search -->
    <div class="px-4 pb-3 shrink-0">
      <div class="relative">
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
        </svg>
        <input
          v-model="search"
          type="text"
          placeholder="搜索研究问题…"
          class="w-full bg-bg-elevated border border-border rounded-xl pl-9 pr-3 py-2 text-[13px] text-text-primary outline-none focus:border-tinder-purple placeholder:text-text-muted"
        />
      </div>
    </div>

    <LoadingState v-if="loading" class="flex-1" message="加载研究库…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else>
      <!-- Empty state -->
      <div v-if="sessions.length === 0" class="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <div class="w-16 h-16 rounded-2xl bg-bg-elevated flex items-center justify-center">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
        </div>
        <div class="text-center">
          <p class="text-[15px] font-semibold text-text-primary mb-1">暂无已保存的研究</p>
          <p class="text-[13px] text-text-muted">完成深度研究后点击保存，即可在此查看已保存的研究</p>
        </div>
        <button
          type="button"
          class="px-5 py-2.5 rounded-xl text-[13px] font-semibold text-white"
          style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
          @click="router.push('/research')"
        >
          去深度研究
        </button>
      </div>

      <!-- No search results -->
      <div v-else-if="filteredSessions.length === 0" class="flex-1 flex items-center justify-center">
        <p class="text-[13px] text-text-muted">没有匹配的研究记录</p>
      </div>

      <!-- Session list -->
      <div v-else class="flex-1 overflow-y-auto">
        <div class="px-4 pb-4 pt-1 space-y-2">
          <button
            v-for="session in filteredSessions"
            :key="session.id"
            type="button"
            class="w-full text-left card-section active:opacity-70 transition-opacity"
            @click="openSession(session)"
          >
            <div class="flex items-start gap-3">
              <div
                class="w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5"
                style="background: color-mix(in srgb, var(--color-tinder-purple) 15%, transparent);"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--color-tinder-purple);">
                  <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                </svg>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-[14px] font-medium text-text-primary line-clamp-2">{{ session.question }}</p>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-[11px]" :class="statusColor(session.status)">{{ statusLabel(session.status) }}</span>
                  <span class="text-[11px] text-text-muted">·</span>
                  <span class="text-[11px] text-text-muted">{{ session.paper_ids.length }} 篇论文</span>
                  <span class="text-[11px] text-text-muted">·</span>
                  <span class="text-[11px] text-text-muted">{{ formatDate(session.created_at) }}</span>
                </div>
              </div>
              <button
                type="button"
                class="w-8 h-8 flex items-center justify-center text-text-muted shrink-0 -mr-1"
                @click.stop="openMenu(session)"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
                </svg>
              </button>
            </div>
          </button>
        </div>
      </div>
    </template>

    <!-- Context menu -->
    <BottomSheet :visible="menuVisible" @close="menuVisible = false">
      <div class="pb-4">
        <button
          type="button"
          class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-text-secondary active:bg-bg-hover"
          @click="doUnsave"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
          </svg>
          从研究库移除
        </button>
        <button
          type="button"
          class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-tinder-pink active:bg-bg-hover"
          @click="doDelete"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
          删除研究
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
