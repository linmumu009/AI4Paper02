<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import PaperListItem from '@/components/PaperListItem.vue'
import {
  fetchResearchSessions,
  fetchResearchStream,
  fetchResearchFollowup,
  saveResearchSession,
  deleteResearchSession,
  fetchKbTree,
  downloadResearchResult,
} from '@shared/api'
import type { ResearchSession, ResearchSseEvent } from '@shared/types/research'
import type { KbTree, KbFolder, KbPaper } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'ResearchView' })

const router = useRouter()
const route = useRoute()

// ── List mode ──────────────────────────────────────────────────────────────
type View = 'list' | 'new' | 'session'
const currentView = ref<View>('list')
const sessions = ref<ResearchSession[]>([])
const listLoading = ref(true)
const listError = ref('')
const listSearch = ref('')

// ── New research ───────────────────────────────────────────────────────────
const questionText = ref('')
const kbTree = ref<KbTree | null>(null)
const kbLoading = ref(false)
const pickerVisible = ref(false)
const pickerSearch = ref('')
const selectedPapers = ref<KbPaper[]>([])

// ── Active session ─────────────────────────────────────────────────────────
const activeSession = ref<ResearchSession | null>(null)
const streamContent = ref<Array<{ round: number; title: string; text: string }>>([])
const currentRound = ref(0)
const totalRounds = ref(3)
const streamStatus = ref<'idle' | 'streaming' | 'done' | 'error'>('idle')
const streamError = ref('')
const sessionId = ref<number | null>(null)

// ── Followup ───────────────────────────────────────────────────────────────
const followupText = ref('')
const sendingFollowup = ref(false)
const followupContent = ref('')
const downloadSheetVisible = ref(false)

function openDownloadSheet() { downloadSheetVisible.value = true }

function doDownloadResult(format: 'md' | 'docx' | 'pdf') {
  if (!sessionId.value) return
  downloadResearchResult(sessionId.value, format)
  showToast('已开始下载')
  downloadSheetVisible.value = false
}

async function loadSessions() {
  listLoading.value = true
  listError.value = ''
  try {
    const res = await fetchResearchSessions(50)
    sessions.value = res.sessions
  } catch (e: any) {
    listError.value = e?.message || '加载失败'
  } finally {
    listLoading.value = false
  }
}

onMounted(async () => {
  await loadSessions()
  const qId = route.query.session_id
  if (qId) {
    const sid = Number(qId)
    const found = sessions.value.find((s) => s.id === sid)
    if (found) viewSession(found)
  }
})

const filteredSessions = computed(() => {
  const q = listSearch.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter((s) => s.question.toLowerCase().includes(q))
})

async function loadKbForPicker() {
  if (kbTree.value) return
  kbLoading.value = true
  try {
    kbTree.value = await fetchKbTree('kb')
  } finally {
    kbLoading.value = false
  }
}

function getAllKbPapers(): KbPaper[] {
  if (!kbTree.value) return []
  const result: KbPaper[] = [...kbTree.value.papers]
  function collect(f: KbFolder) { result.push(...f.papers); f.children.forEach(collect) }
  kbTree.value.folders.forEach(collect)
  return result
}

const filteredPickerPapers = computed(() => {
  const q = pickerSearch.value.trim().toLowerCase()
  const selected = new Set(selectedPapers.value.map((p) => p.paper_id))
  return getAllKbPapers().filter((p) => {
    if (selected.has(p.paper_id)) return false
    if (!q) return true
    const title = (p.paper_data?.short_title || p.paper_data?.['📖标题'] || '').toLowerCase()
    return title.includes(q) || (p.paper_data?.institution || '').toLowerCase().includes(q)
  })
})

async function openPicker() {
  await loadKbForPicker()
  pickerSearch.value = ''
  pickerVisible.value = true
}

function togglePaper(paper: KbPaper) {
  const idx = selectedPapers.value.findIndex((p) => p.paper_id === paper.paper_id)
  if (idx >= 0) selectedPapers.value.splice(idx, 1)
  else {
    if (selectedPapers.value.length >= 10) { showToast('最多选择 10 篇'); return }
    selectedPapers.value.push(paper)
  }
}

async function startResearch() {
  if (!questionText.value.trim()) return
  currentView.value = 'session'
  streamContent.value = []
  currentRound.value = 0
  streamStatus.value = 'streaming'
  streamError.value = ''
  sessionId.value = null
  followupContent.value = ''
  followupText.value = ''

  try {
    const resp = await fetchResearchStream({
      question: questionText.value.trim(),
      paper_ids: selectedPapers.value.map((p) => p.paper_id),
      config: { top_n: 10 },
    })
    if (!resp.ok) { streamStatus.value = 'error'; streamError.value = '研究请求失败'; return }
    const reader = resp.body?.getReader()
    if (!reader) { streamStatus.value = 'error'; streamError.value = '无法读取响应'; return }
    const decoder = new TextDecoder()
    let buffer = ''
    let roundMap: Map<number, number> = new Map()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') continue
        try {
          const evt = JSON.parse(payload) as ResearchSseEvent
          switch (evt.type) {
            case 'session_created':
              sessionId.value = evt.session_id
              break
            case 'round_start': {
              currentRound.value = evt.round
              const title = evt.title || `第 ${evt.round} 轮`
              const idx = streamContent.value.findIndex((c) => c.round === evt.round)
              if (idx < 0) {
                streamContent.value.push({ round: evt.round, title, text: '' })
                roundMap.set(evt.round, streamContent.value.length - 1)
              }
              break
            }
            case 'text': {
              const idx = roundMap.get(evt.round) ?? -1
              if (idx >= 0) streamContent.value[idx].text += evt.content
              break
            }
            case 'final_answer':
              streamStatus.value = 'done'
              break
            case 'error':
              streamError.value = evt.content
              streamStatus.value = 'error'
              break
          }
        } catch { /* ignore parse errors */ }
      }
    }
    if (streamStatus.value !== 'error') streamStatus.value = 'done'
    await loadSessions()
  } catch (e: any) {
    streamError.value = e?.message || '研究失败'
    streamStatus.value = 'error'
  }
}

async function sendFollowup() {
  if (!followupText.value.trim() || !sessionId.value || sendingFollowup.value) return
  sendingFollowup.value = true
  const q = followupText.value.trim()
  followupText.value = ''
  followupContent.value = ''
  try {
    const resp = await fetchResearchFollowup(sessionId.value, q)
    if (!resp.ok) { showToast('追问失败'); return }
    const reader = resp.body?.getReader()
    if (!reader) return
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') continue
          try {
            const evt = JSON.parse(payload) as any
            if (evt.type === 'text') followupContent.value += evt.content
          } catch { /* ignore */ }
        }
      }
    }
  } finally {
    sendingFollowup.value = false
  }
}

async function viewSession(session: ResearchSession) {
  activeSession.value = session
  sessionId.value = session.id
  streamStatus.value = 'done'
  streamError.value = ''
  followupContent.value = ''
  followupText.value = ''
  // Reconstruct content from rounds
  streamContent.value = (session.rounds ?? []).map((r) => ({
    round: r.round_number,
    title: `第 ${r.round_number} 轮：${r.round_type === 'relevance' ? '相关性分析' : r.round_type === 'summary_analysis' ? '摘要分析' : '全文精读'}`,
    text: typeof r.output?.content === 'string' ? r.output.content : JSON.stringify(r.output).slice(0, 2000),
  }))
  currentView.value = 'session'
}

async function toggleSave(session: ResearchSession) {
  try {
    await saveResearchSession(session.id, !session.saved)
    session.saved = !session.saved
    showToast(session.saved ? '已保存' : '已取消保存')
  } catch { showToast('操作失败') }
}

async function doDelete(session: ResearchSession) {
  try {
    await showDialog({
      title: '删除研究', message: '确定删除此研究会话？',
      confirmButtonText: '删除', cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteResearchSession(session.id)
    sessions.value = sessions.value.filter((s) => s.id !== session.id)
    showToast('已删除')
  } catch { /* user cancelled */ }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">

    <!-- ── List view ── -->
    <template v-if="currentView === 'list'">
      <PageHeader title="深度研究" :show-back="false">
        <template #right>
          <button
            type="button"
            class="w-10 h-10 flex items-center justify-center text-text-secondary"
            @click="currentView = 'new'; selectedPapers = []; questionText = ''"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        </template>
      </PageHeader>
      <div class="px-4 pb-2 shrink-0">
        <SearchBar v-model="listSearch" placeholder="搜索研究问题…" />
      </div>
      <LoadingState v-if="listLoading" class="flex-1" message="加载研究会话…" />
      <ErrorState v-else-if="listError" class="flex-1" :message="listError" @retry="loadSessions" />
      <div v-else class="flex-1 overflow-y-auto">
        <EmptyState v-if="filteredSessions.length === 0" title="还没有研究" description="点击右上角「+」开始一次深度研究" />
        <div v-else class="pb-4">
          <div
            v-for="session in filteredSessions"
            :key="session.id"
            class="mx-4 mb-3 card-section cursor-pointer active:scale-[0.99] transition-transform"
            @click="viewSession(session)"
          >
            <div class="flex items-start justify-between gap-2 mb-2">
              <p class="text-[14px] font-semibold text-text-primary line-clamp-2 leading-snug flex-1">{{ session.question }}</p>
              <div class="flex items-center gap-1 shrink-0">
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="session.status === 'done' ? 'bg-tinder-green/15 text-tinder-green' : session.status === 'error' ? 'bg-tinder-pink/15 text-tinder-pink' : 'bg-tinder-blue/15 text-tinder-blue'"
                >
                  {{ session.status === 'done' ? '完成' : session.status === 'error' ? '失败' : '进行中' }}
                </span>
              </div>
            </div>
            <div class="flex items-center gap-3 text-[11px] text-text-muted">
              <span>{{ session.paper_ids.length }} 篇论文</span>
              <span v-if="session.saved" class="text-tinder-green">已保存</span>
              <span class="ml-auto">{{ new Date(session.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ── New research view ── -->
    <template v-else-if="currentView === 'new'">
      <PageHeader title="新建研究" @back="currentView = 'list'" />
      <div class="flex-1 overflow-y-auto pb-28 px-4 pt-2 space-y-4">
        <div>
          <label class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-2 block">研究问题</label>
          <textarea
            v-model="questionText"
            placeholder="输入你想深度研究的问题，AI 将从你的论文知识库中寻找答案…"
            class="input-field resize-none"
            rows="4"
            maxlength="500"
          />
          <p class="text-[11px] text-text-muted text-right mt-1">{{ questionText.length }} / 500</p>
        </div>

        <!-- Paper selection -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="text-[12px] font-semibold text-text-muted uppercase tracking-wider">论文范围（选填）</label>
            <span class="text-[11px] text-text-muted">{{ selectedPapers.length === 0 ? '全部知识库' : `已选 ${selectedPapers.length} 篇` }}</span>
          </div>
          <div v-if="selectedPapers.length > 0" class="space-y-2 mb-2">
            <div
              v-for="paper in selectedPapers"
              :key="paper.paper_id"
              class="flex items-center gap-2 p-2.5 rounded-xl bg-bg-elevated border border-border"
            >
              <p class="text-[12px] text-text-primary flex-1 line-clamp-1">{{ paper.paper_data?.short_title || paper.paper_id }}</p>
              <button type="button" class="text-tinder-pink" @click="togglePaper(paper)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
          <button
            type="button"
            class="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-border text-text-muted text-[13px] active:bg-bg-hover"
            @click="openPicker"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {{ selectedPapers.length === 0 ? '选择特定论文（留空=全库）' : '添加更多论文' }}
          </button>
        </div>
      </div>

      <!-- CTA -->
      <div class="shrink-0 px-4 pt-3 border-t border-border bg-bg-card" style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px));">
        <button type="button" class="btn-primary" :disabled="!questionText.trim()" @click="startResearch">
          开始深度研究
        </button>
      </div>
    </template>

    <!-- ── Session view ── -->
    <template v-else-if="currentView === 'session'">
      <PageHeader :title="activeSession?.question || questionText || '研究结果'" @back="currentView = 'list'">
        <template #right>
          <div class="flex items-center gap-1">
            <button
              v-if="sessionId && streamStatus === 'done'"
              type="button"
              class="w-10 h-10 flex items-center justify-center text-text-secondary active:text-tinder-blue"
              aria-label="导出报告"
              @click="openDownloadSheet"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
            </button>
            <button
              v-if="sessionId && streamStatus === 'done'"
              type="button"
              class="w-10 h-10 flex items-center justify-center"
              @click="activeSession && toggleSave(activeSession)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" :class="activeSession?.saved ? 'text-tinder-green' : 'text-text-muted'">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" :fill="activeSession?.saved ? 'currentColor' : 'none'" />
              </svg>
            </button>
          </div>
        </template>
      </PageHeader>

      <!-- Progress bar (during streaming) -->
      <div v-if="streamStatus === 'streaming'" class="px-4 pb-3 shrink-0">
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-[12px] text-text-muted">第 {{ currentRound }} 轮分析…</span>
          <div class="w-4 h-4 border-2 border-tinder-pink border-t-transparent rounded-full animate-spin" />
        </div>
        <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
          <div
            class="h-full rounded-full transition-all duration-500"
            style="background: linear-gradient(90deg, var(--color-gradient-start), var(--color-gradient-end));"
            :style="{ width: `${Math.min(100, (currentRound / 3) * 100)}%` }"
          />
        </div>
      </div>

      <!-- Error state -->
      <div v-if="streamStatus === 'error'" class="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <p class="text-tinder-pink text-[14px] text-center">{{ streamError || '研究失败，请重试' }}</p>
        <button type="button" class="btn-ghost" @click="currentView = 'new'">重新开始</button>
      </div>

      <template v-else>
        <!-- Stream rounds content -->
        <div class="flex-1 overflow-y-auto pb-32">
          <div class="px-4 pt-2 space-y-4">
            <div
              v-for="block in streamContent"
              :key="block.round"
              class="card-section"
            >
              <div class="flex items-center gap-2 mb-3">
                <div class="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white" style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));">
                  {{ block.round }}
                </div>
                <span class="text-[13px] font-semibold text-text-primary">{{ block.title }}</span>
              </div>
              <MarkdownRenderer :content="block.text" />
            </div>

            <!-- Followup answer -->
            <div v-if="followupContent" class="card-section border-tinder-blue/30">
              <p class="section-title">追问回答</p>
              <MarkdownRenderer :content="followupContent" />
            </div>

            <!-- Research done banner -->
            <div v-if="streamStatus === 'done'" class="rounded-2xl border border-border bg-bg-elevated/50 px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="w-7 h-7 rounded-full border border-border flex items-center justify-center shrink-0">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-text-muted">
                    <path d="m20 6-11 11-5-5"/>
                  </svg>
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-[13px] font-medium text-text-secondary">研究完成</p>
                </div>
                <button
                  type="button"
                  class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] font-medium transition-all active:scale-95"
                  :class="activeSession?.saved
                    ? 'border-tinder-green/40 text-tinder-green cursor-default'
                    : 'border-border text-text-secondary active:opacity-70'"
                  :disabled="activeSession?.saved"
                  @click="activeSession && toggleSave(activeSession)"
                >
                  <svg v-if="!activeSession?.saved" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
                  </svg>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <path d="m20 6-11 11-5-5"/>
                  </svg>
                  {{ activeSession?.saved ? '已保存' : '保存到研究库' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Followup input (fixed bottom, shown when done) -->
        <div
          v-if="streamStatus === 'done'"
          class="shrink-0 border-t border-border bg-bg-card px-4 pt-3"
          style="padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));"
        >
          <div class="flex items-end gap-2">
            <textarea
              v-model="followupText"
              placeholder="追问…"
              class="flex-1 bg-bg-elevated border border-border rounded-2xl px-3 py-2.5 text-[13px] text-text-primary resize-none outline-none focus:border-tinder-pink max-h-20"
              rows="1"
              @keydown.enter.prevent="sendFollowup"
            />
            <button
              type="button"
              class="shrink-0 w-10 h-10 rounded-2xl flex items-center justify-center"
              :class="followupText.trim() && !sendingFollowup ? 'bg-tinder-pink text-white' : 'bg-bg-elevated text-text-muted'"
              :disabled="!followupText.trim() || sendingFollowup"
              @click="sendFollowup"
            >
              <svg v-if="sendingFollowup" class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- Paper picker -->
    <BottomSheet :visible="pickerVisible" title="选择研究范围" height="80dvh" @close="pickerVisible = false">
      <div class="px-4 pb-2 pt-1">
        <SearchBar v-model="pickerSearch" placeholder="搜索论文…" />
      </div>
      <LoadingState v-if="kbLoading" message="加载知识库…" />
      <div v-else-if="filteredPickerPapers.length === 0" class="px-4 py-8 text-center text-[13px] text-text-muted">
        {{ pickerSearch ? '没有匹配结果' : '知识库为空' }}
      </div>
      <div v-else class="pb-4">
        <PaperListItem
          v-for="paper in filteredPickerPapers"
          :key="paper.paper_id"
          :paper="paper"
          @click="togglePaper(paper)"
        />
      </div>
    </BottomSheet>

    <!-- Download format sheet -->
    <BottomSheet :visible="downloadSheetVisible" title="导出报告" @close="downloadSheetVisible = false">
      <div class="pb-4">
        <button type="button" class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left" @click="doDownloadResult('md')">
          <div class="w-9 h-9 rounded-xl bg-tinder-green/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-green">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <p class="text-[14px] font-medium text-text-primary">Markdown (.md)</p>
            <p class="text-[12px] text-text-muted mt-0.5">适合进一步编辑</p>
          </div>
        </button>
        <button type="button" class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left" @click="doDownloadResult('docx')">
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <p class="text-[14px] font-medium text-text-primary">Word (.docx)</p>
            <p class="text-[12px] text-text-muted mt-0.5">适合分享与打印</p>
          </div>
        </button>
        <button type="button" class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left" @click="doDownloadResult('pdf')">
          <div class="w-9 h-9 rounded-xl bg-tinder-pink/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-pink">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <p class="text-[14px] font-medium text-text-primary">PDF (.pdf)</p>
            <p class="text-[12px] text-text-muted mt-0.5">适合存档</p>
          </div>
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
