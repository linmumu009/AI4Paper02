<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { KbFolder, KbPaper, KbTree, PaperSummary } from '../../types/paper'
import ImmersivePaperReader from './ImmersivePaperReader.vue'
import PaperInspector from './PaperInspector.vue'
import bookIcon from '../../assets/heroicons/book-open.svg'
import checkIcon from '../../assets/heroicons/check-circle.svg'
import closeIcon from '../../assets/heroicons/x-mark.svg'
import documentIcon from '../../assets/heroicons/document-text.svg'
import folderIcon from '../../assets/heroicons/folder.svg'
import scaleIcon from '../../assets/heroicons/scale.svg'
import beakerIcon from '../../assets/heroicons/beaker.svg'

type SortMode = 'saved_desc' | 'relevance_desc' | 'title_asc'
type StatusFilter = 'all' | 'unread' | 'reading' | 'read'

interface PaperEntry {
  paper: KbPaper
  folderId: number | null
  folderName: string
  folderPath: string
}

const props = defineProps<{
  kbTree: KbTree
  activeFolderId: number | null
}>()

const emit = defineEmits<{
  openPaper: [paperId: string]
  openPdf: [paper: KbPaper]
  compare: [paperIds: string[]]
  research: [paperIds: string[], paperTitles: Record<string, string>]
  removePaper: [paper: KbPaper]
  updateReadStatus: [paper: KbPaper, status: 'unread' | 'reading' | 'read']
  showSidebar: []
}>()

const search = ref('')
const sortMode = ref<SortMode>('saved_desc')
const statusFilter = ref<StatusFilter>('all')
const activePaperId = ref<string | null>(null)
const selectedPaperIds = ref<Set<string>>(new Set())
const inspectorOpen = ref(false)
const immersiveOpen = ref(false)
const rowsRef = ref<HTMLElement | null>(null)
const listScrollTopBeforeImmersive = ref(0)

function titleOf(paper: KbPaper) {
  return paper.paper_data.short_title || paper.paper_data['📖标题'] || paper.paper_id
}

function scoreOf(summary: PaperSummary) {
  if (summary.relevance_score == null) return null
  return Math.round(summary.relevance_score <= 1 ? summary.relevance_score * 100 : summary.relevance_score)
}

function collectFolderEntries(folder: KbFolder, parents: string[]): PaperEntry[] {
  const path = [...parents, folder.name]
  return [
    ...folder.papers.map(paper => ({ paper, folderId: folder.id, folderName: folder.name, folderPath: path.join(' / ') })),
    ...folder.children.flatMap(child => collectFolderEntries(child, path)),
  ]
}

function findFolder(folders: KbFolder[], id: number): KbFolder | null {
  for (const folder of folders) {
    if (folder.id === id) return folder
    const nested = findFolder(folder.children, id)
    if (nested) return nested
  }
  return null
}

const allEntries = computed<PaperEntry[]>(() => [
  ...props.kbTree.papers.map(paper => ({ paper, folderId: null, folderName: '未分类', folderPath: '知识库' })),
  ...props.kbTree.folders.flatMap(folder => collectFolderEntries(folder, [])),
])

const activeFolder = computed(() => props.activeFolderId == null ? null : findFolder(props.kbTree.folders, props.activeFolderId))
const activeFolderEntries = computed(() => {
  if (!activeFolder.value) return allEntries.value
  return collectFolderEntries(activeFolder.value, []).map(entry => ({ ...entry, folderPath: entry.folderPath }))
})

const visibleEntries = computed(() => {
  const query = search.value.trim().toLowerCase()
  const entries = activeFolderEntries.value.filter(({ paper, folderPath }) => {
    if (statusFilter.value !== 'all' && (paper.read_status || 'unread') !== statusFilter.value) return false
    if (!query) return true
    const summary = paper.paper_data
    return [titleOf(paper), summary['📖标题'], summary.institution, summary.abstract, summary.authors?.join(' '), folderPath, paper.paper_id]
      .filter(Boolean).join(' ').toLowerCase().includes(query)
  })
  return [...entries].sort((a, b) => {
    if (sortMode.value === 'title_asc') return titleOf(a.paper).localeCompare(titleOf(b.paper), 'zh-CN')
    if (sortMode.value === 'relevance_desc') return (scoreOf(b.paper.paper_data) ?? -1) - (scoreOf(a.paper.paper_data) ?? -1)
    return b.paper.created_at.localeCompare(a.paper.created_at)
  })
})

const activeEntry = computed(() => visibleEntries.value.find(entry => entry.paper.paper_id === activePaperId.value) ?? null)
const activeSummary = computed(() => activeEntry.value?.paper.paper_data ?? null)
const activeIndex = computed(() => visibleEntries.value.findIndex(entry => entry.paper.paper_id === activePaperId.value))
const immersiveRelatedPapers = computed(() => {
  const active = activeSummary.value
  if (!active) return []
  const categories = new Set(active.categories ?? [])
  const overlap = (paper: PaperSummary) => (paper.categories ?? []).filter(category => categories.has(category)).length
  return visibleEntries.value
    .map(entry => entry.paper.paper_data)
    .filter(paper => paper.paper_id !== active.paper_id)
    .sort((a, b) => overlap(b) - overlap(a) || (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
    .slice(0, 4)
})
const selectedEntries = computed(() => allEntries.value.filter(entry => selectedPaperIds.value.has(entry.paper.paper_id)))
const selectedTitles = computed(() => Object.fromEntries(selectedEntries.value.map(entry => [entry.paper.paper_id, titleOf(entry.paper)])))
const unreadCount = computed(() => allEntries.value.filter(entry => (entry.paper.read_status || 'unread') === 'unread').length)
const readingCount = computed(() => allEntries.value.filter(entry => entry.paper.read_status === 'reading').length)

watch(visibleEntries, (entries) => {
  if (!entries.some(entry => entry.paper.paper_id === activePaperId.value)) activePaperId.value = entries[0]?.paper.paper_id ?? null
  if (!entries.length) immersiveOpen.value = false
}, { immediate: true })

watch(() => props.activeFolderId, () => {
  selectedPaperIds.value = new Set()
  immersiveOpen.value = false
})

function selectPaper(paper: KbPaper) {
  activePaperId.value = paper.paper_id
  inspectorOpen.value = true
}

function openImmersive(paper?: KbPaper) {
  if (paper) activePaperId.value = paper.paper_id
  if (!activeEntry.value) return
  listScrollTopBeforeImmersive.value = rowsRef.value?.scrollTop ?? 0
  inspectorOpen.value = false
  immersiveOpen.value = true
}

function closeImmersive() {
  immersiveOpen.value = false
  void nextTick(() => {
    if (rowsRef.value) rowsRef.value.scrollTop = listScrollTopBeforeImmersive.value
  })
}

function navigateImmersive(delta: -1 | 1) {
  const nextIndex = Math.max(0, Math.min(activeIndex.value + delta, visibleEntries.value.length - 1))
  const next = visibleEntries.value[nextIndex]
  if (next) activePaperId.value = next.paper.paper_id
}

function openRelatedPaper(paperId: string) {
  if (visibleEntries.value.some(entry => entry.paper.paper_id === paperId)) activePaperId.value = paperId
}

function compareActivePaper() {
  const active = activeEntry.value?.paper
  const related = immersiveRelatedPapers.value[0]
  if (active && related) emit('compare', [active.paper_id, related.paper_id])
}

function completeActiveReading() {
  const active = activeEntry.value?.paper
  if (!active) return
  emit('updateReadStatus', active, 'read')
  if (activeIndex.value < visibleEntries.value.length - 1) navigateImmersive(1)
}

function handleWorkspaceKeydown(event: KeyboardEvent) {
  if (!immersiveOpen.value) return
  const target = event.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeImmersive()
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp' || event.key === 'j' || event.key === 'J') {
    event.preventDefault()
    navigateImmersive(-1)
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown' || event.key === 'k' || event.key === 'K') {
    event.preventDefault()
    navigateImmersive(1)
  }
}

onMounted(() => window.addEventListener('keydown', handleWorkspaceKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleWorkspaceKeydown))

function toggleSelection(paperId: string) {
  const next = new Set(selectedPaperIds.value)
  next.has(paperId) ? next.delete(paperId) : next.add(paperId)
  selectedPaperIds.value = next
}

function toggleAllVisible() {
  const visibleIds = visibleEntries.value.map(entry => entry.paper.paper_id)
  const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedPaperIds.value.has(id))
  const next = new Set(selectedPaperIds.value)
  visibleIds.forEach(id => allSelected ? next.delete(id) : next.add(id))
  selectedPaperIds.value = next
}

function startSelectedResearch() {
  const ids = selectedEntries.value.map(entry => entry.paper.paper_id)
  if (ids.length) emit('research', ids, selectedTitles.value)
}

function compareSelected() {
  const ids = selectedEntries.value.map(entry => entry.paper.paper_id)
  if (ids.length >= 2) emit('compare', ids)
}

function nextReadStatus(paper: KbPaper): 'unread' | 'reading' | 'read' {
  if (paper.read_status === 'reading') return 'read'
  if (paper.read_status === 'read') return 'unread'
  return 'reading'
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<template>
  <ImmersivePaperReader
    v-if="immersiveOpen && activeEntry"
    :key="activeEntry.paper.paper_id"
    :paper="activeEntry.paper.paper_data"
    :related-papers="immersiveRelatedPapers"
    :publication-date="formatDate(activeEntry.paper.created_at)"
    :position="activeIndex + 1"
    :total="visibleEntries.length"
    :collected="true"
    :bookmarked="activeEntry.paper.read_status === 'reading'"
    :can-go-previous="activeIndex > 0"
    :can-go-next="activeIndex < visibleEntries.length - 1"
    :can-compare="immersiveRelatedPapers.length > 0"
    return-label="返回知识库"
    decision-mode="knowledge"
    source-scope="kb"
    @exit="closeImmersive"
    @previous="navigateImmersive(-1)"
    @next="navigateImmersive(1)"
    @skip="completeActiveReading"
    @compare="compareActivePaper"
    @collect="emit('removePaper', activeEntry.paper)"
    @open-pdf="emit('openPdf', activeEntry.paper)"
    @open-detail="emit('openPaper', activeEntry.paper.paper_id)"
    @toggle-bookmark="emit('updateReadStatus', activeEntry.paper, activeEntry.paper.read_status === 'reading' ? 'unread' : 'reading')"
    @start-research="emit('research', [activeEntry.paper.paper_id], { [activeEntry.paper.paper_id]: titleOf(activeEntry.paper) })"
    @select-related="openRelatedPaper"
  />

  <section v-else class="knowledge-workspace" aria-label="知识库论文工作区">
    <div class="knowledge-workspace__list-pane">
      <header class="knowledge-workspace__header">
        <div class="knowledge-workspace__title-row">
          <div>
            <span>Knowledge library</span>
            <h1>{{ activeFolder?.name || '全部知识' }}</h1>
            <p>{{ visibleEntries.length }} 篇论文 · {{ unreadCount }} 篇待读 · {{ readingCount }} 篇阅读中</p>
          </div>
          <button class="knowledge-workspace__folders-button" type="button" @click="emit('showSidebar')">
            <img :src="folderIcon" alt="">文件夹
          </button>
        </div>

        <div class="knowledge-workspace__filters">
          <label class="knowledge-workspace__search">
            <span class="sr-only">搜索知识库</span>
            <input v-model="search" type="search" placeholder="搜索标题、作者、机构或文件夹…">
          </label>
          <select v-model="statusFilter" aria-label="阅读状态">
            <option value="all">全部状态</option><option value="unread">待读</option><option value="reading">阅读中</option><option value="read">已读</option>
          </select>
          <select v-model="sortMode" aria-label="排序方式">
            <option value="saved_desc">最近收藏</option><option value="relevance_desc">相关度</option><option value="title_asc">标题 A–Z</option>
          </select>
        </div>

        <div v-if="selectedPaperIds.size" class="knowledge-workspace__batchbar">
          <strong>已选 {{ selectedPaperIds.size }} 篇</strong>
          <button type="button" :disabled="selectedPaperIds.size < 2" @click="compareSelected"><img :src="scaleIcon" alt="">加入对比</button>
          <button type="button" @click="startSelectedResearch"><img :src="beakerIcon" alt="">深度研究</button>
          <button type="button" @click="selectedPaperIds = new Set()">清除</button>
        </div>
      </header>

      <div class="knowledge-workspace__columns">
        <label><input type="checkbox" :checked="visibleEntries.length > 0 && visibleEntries.every(entry => selectedPaperIds.has(entry.paper.paper_id))" @change="toggleAllVisible">论文信息</label>
        <span>相关度</span><span>笔记</span><span>收藏时间</span><span>状态</span>
      </div>

      <div v-if="visibleEntries.length" ref="rowsRef" class="knowledge-workspace__rows" role="listbox" aria-label="知识库论文">
        <article
          v-for="entry in visibleEntries"
          :key="entry.paper.paper_id"
          class="knowledge-workspace__row"
          :class="{ 'is-active': activePaperId === entry.paper.paper_id, 'is-selected': selectedPaperIds.has(entry.paper.paper_id) }"
          role="option"
          :aria-selected="activePaperId === entry.paper.paper_id"
          tabindex="0"
          @click="selectPaper(entry.paper)"
          @dblclick="openImmersive(entry.paper)"
          @keydown.enter="openImmersive(entry.paper)"
        >
          <div class="knowledge-workspace__paper-cell">
            <input type="checkbox" :checked="selectedPaperIds.has(entry.paper.paper_id)" :aria-label="`选择论文：${titleOf(entry.paper)}`" @click.stop @change="toggleSelection(entry.paper.paper_id)">
            <div>
              <div class="knowledge-workspace__tags"><span>{{ entry.folderName }}</span><span v-if="entry.paper.paper_data.institution">{{ entry.paper.paper_data.institution }}</span></div>
              <h2>{{ titleOf(entry.paper) }}</h2>
              <p>{{ entry.paper.paper_data.authors?.slice(0, 3).join(', ') || entry.paper.paper_id }}</p>
            </div>
          </div>
          <strong class="knowledge-workspace__score">{{ scoreOf(entry.paper.paper_data) ?? '—' }}</strong>
          <span class="knowledge-workspace__notes"><img :src="documentIcon" alt="">{{ entry.paper.note_count || 0 }}</span>
          <time :datetime="entry.paper.created_at">{{ formatDate(entry.paper.created_at) }}</time>
          <button class="knowledge-workspace__status" type="button" :class="`is-${entry.paper.read_status || 'unread'}`" @click.stop="emit('updateReadStatus', entry.paper, nextReadStatus(entry.paper))">
            {{ entry.paper.read_status === 'read' ? '已读' : entry.paper.read_status === 'reading' ? '阅读中' : '待读' }}
          </button>
        </article>
      </div>

      <div v-else class="knowledge-workspace__empty">
        <img :src="bookIcon" alt=""><h2>{{ search || statusFilter !== 'all' ? '没有符合条件的论文' : '这个文件夹还没有论文' }}</h2>
        <p>{{ search || statusFilter !== 'all' ? '调整搜索词或阅读状态后再试。' : '从今日论文收藏内容，或在左侧把论文移动到这个文件夹。' }}</p>
        <button v-if="search || statusFilter !== 'all'" type="button" @click="search = ''; statusFilter = 'all'">清除筛选</button>
      </div>

      <footer class="knowledge-workspace__footer"><img :src="checkIcon" alt="">当前显示 {{ visibleEntries.length }} / {{ allEntries.length }} 篇论文</footer>
    </div>

    <button v-if="inspectorOpen" class="knowledge-workspace__backdrop" type="button" aria-label="关闭论文详情遮罩" @click="inspectorOpen = false" />
    <div class="knowledge-workspace__inspector" :class="{ 'is-open': inspectorOpen }">
      <button class="knowledge-workspace__close" type="button" aria-label="关闭论文详情" @click="inspectorOpen = false"><img :src="closeIcon" alt=""></button>
      <PaperInspector
        :paper="activeSummary"
        :publication-date="activeEntry ? formatDate(activeEntry.paper.created_at) : ''"
        :collected="true"
        :bookmarked="activeEntry?.paper.read_status === 'reading'"
        collection-action-label="从知识库移除"
        collection-action-tone="danger"
        :project-action-primary="true"
        source-scope="kb"
        @open-detail="activeEntry && openImmersive(activeEntry.paper)"
        @open-pdf="activeEntry && emit('openPdf', activeEntry.paper)"
        @collect="activeEntry && emit('removePaper', activeEntry.paper)"
        @toggle-bookmark="activeEntry && emit('updateReadStatus', activeEntry.paper, activeEntry.paper.read_status === 'reading' ? 'unread' : 'reading')"
        @start-research="activeEntry && emit('research', [activeEntry.paper.paper_id], { [activeEntry.paper.paper_id]: titleOf(activeEntry.paper) })"
      />
    </div>
  </section>
</template>

<style scoped>
.knowledge-workspace{--kw-line:var(--color-border);--kw-muted:var(--color-text-muted);display:grid;width:100%;height:100%;min-width:0;min-height:0;grid-template-columns:minmax(0,1fr) clamp(380px,34vw,520px);overflow:hidden;background:var(--color-bg);color:var(--color-text-primary)}.knowledge-workspace img{display:block}.knowledge-workspace button,.knowledge-workspace input,.knowledge-workspace select{font:inherit}.knowledge-workspace__list-pane{display:flex;min-width:0;min-height:0;flex-direction:column;overflow:hidden}.knowledge-workspace__header{flex:0 0 auto;padding:19px 20px 12px;border-bottom:1px solid var(--kw-line);background:var(--color-bg-card)}.knowledge-workspace__title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.knowledge-workspace__title-row span{color:var(--color-tinder-pink);font-size:9px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.knowledge-workspace__title-row h1{margin:4px 0 3px;font-size:20px}.knowledge-workspace__title-row p{margin:0;color:var(--kw-muted);font-size:10px}.knowledge-workspace__folders-button{display:none;align-items:center;gap:6px;border:1px solid var(--kw-line);border-radius:8px;padding:8px 10px;background:var(--color-bg-elevated);color:var(--color-text-secondary);font-size:10px;font-weight:700}.knowledge-workspace__folders-button img{width:14px}.knowledge-workspace__filters{display:flex;gap:8px;margin-top:15px}.knowledge-workspace__search{min-width:180px;flex:1}.knowledge-workspace__search input,.knowledge-workspace__filters select{box-sizing:border-box;width:100%;height:34px;border:1px solid var(--kw-line);border-radius:8px;padding:0 10px;outline:0;background:var(--color-bg);color:var(--color-text-primary);font-size:10px}.knowledge-workspace__filters select{width:auto;min-width:100px}.knowledge-workspace__search input:focus,.knowledge-workspace__filters select:focus{border-color:color-mix(in srgb,var(--color-tinder-pink) 55%,var(--kw-line))}.knowledge-workspace__batchbar{display:flex;align-items:center;gap:7px;margin-top:10px;padding:8px 10px;border-radius:9px;background:color-mix(in srgb,var(--color-tinder-pink) 7%,var(--color-bg-elevated));font-size:10px}.knowledge-workspace__batchbar strong{margin-right:auto}.knowledge-workspace__batchbar button{display:flex;align-items:center;gap:5px;border:1px solid color-mix(in srgb,var(--color-tinder-pink) 24%,var(--kw-line));border-radius:7px;padding:6px 8px;background:var(--color-bg-card);color:var(--color-text-secondary);font-weight:700}.knowledge-workspace__batchbar button:disabled{opacity:.4}.knowledge-workspace__batchbar img{width:13px}
.knowledge-workspace__columns,.knowledge-workspace__row{display:grid;grid-template-columns:minmax(250px,1fr) 70px 55px 82px 66px;align-items:center;gap:8px}.knowledge-workspace__columns{flex:0 0 auto;padding:9px 14px;border-bottom:1px solid var(--kw-line);background:var(--color-bg-elevated);color:var(--kw-muted);font-size:9px;font-weight:700}.knowledge-workspace__columns label{display:flex;align-items:center;gap:10px}.knowledge-workspace__columns input,.knowledge-workspace__paper-cell>input{width:14px;height:14px;accent-color:var(--color-tinder-pink)}.knowledge-workspace__rows{flex:1 1 auto;min-height:0;overflow-y:auto}.knowledge-workspace__row{min-height:90px;padding:10px 14px;border-bottom:1px solid color-mix(in srgb,var(--kw-line) 75%,transparent);background:var(--color-bg-card);cursor:pointer;transition:background-color .15s ease,box-shadow .15s ease}.knowledge-workspace__row:hover{background:var(--color-bg-hover)}.knowledge-workspace__row.is-active{background:color-mix(in srgb,var(--color-tinder-pink) 6%,var(--color-bg-card));box-shadow:inset 3px 0 var(--color-tinder-pink)}.knowledge-workspace__row.is-selected{background:color-mix(in srgb,var(--color-tinder-pink) 10%,var(--color-bg-card))}.knowledge-workspace__row:focus-visible{outline:2px solid color-mix(in srgb,var(--color-tinder-pink) 55%,white);outline-offset:-2px}.knowledge-workspace__paper-cell{display:flex;min-width:0;align-items:center;gap:12px}.knowledge-workspace__paper-cell>div{min-width:0}.knowledge-workspace__tags{display:flex;gap:5px;margin-bottom:5px}.knowledge-workspace__tags span{max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-radius:4px;padding:2px 5px;background:var(--color-bg-elevated);color:var(--kw-muted);font-size:8px}.knowledge-workspace__paper-cell h2,.knowledge-workspace__paper-cell p{margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.knowledge-workspace__paper-cell h2{font-size:11px;line-height:1.45}.knowledge-workspace__paper-cell p{margin-top:4px;color:var(--kw-muted);font-size:9px}.knowledge-workspace__score{color:var(--color-tag-score-high);font-size:15px}.knowledge-workspace__notes{display:flex;align-items:center;gap:4px;color:var(--kw-muted);font-size:10px}.knowledge-workspace__notes img{width:13px}.knowledge-workspace__row time{color:var(--kw-muted);font-size:9px}.knowledge-workspace__status{justify-self:start;border:0;border-radius:99px;padding:5px 7px;background:var(--color-bg-elevated);color:var(--kw-muted);font-size:8px;font-weight:800}.knowledge-workspace__status.is-reading{background:#fff3df;color:#9c681d}.knowledge-workspace__status.is-read{background:#e8f8ee;color:#267a48}.knowledge-workspace__empty{display:flex;flex:1;align-items:center;justify-content:center;flex-direction:column;padding:30px;text-align:center}.knowledge-workspace__empty img{width:30px;opacity:.45}.knowledge-workspace__empty h2{margin:12px 0 0;font-size:14px}.knowledge-workspace__empty p{max-width:320px;margin:7px 0 14px;color:var(--kw-muted);font-size:10px;line-height:1.6}.knowledge-workspace__empty button{border:1px solid var(--kw-line);border-radius:8px;padding:7px 10px;background:var(--color-bg-card);color:var(--color-text-secondary);font-size:10px}.knowledge-workspace__footer{display:flex;flex:0 0 auto;align-items:center;justify-content:center;gap:6px;padding:8px;border-top:1px solid var(--kw-line);color:var(--kw-muted);font-size:9px}.knowledge-workspace__footer img{width:13px}.knowledge-workspace__inspector{position:relative;min-width:0;min-height:0;border-left:1px solid var(--kw-line);overflow:hidden;background:var(--color-bg-card)}.knowledge-workspace__close{display:none;position:absolute;z-index:3;right:10px;top:10px;width:30px;height:30px;place-items:center;border:1px solid var(--kw-line);border-radius:8px;background:var(--color-bg-card)}.knowledge-workspace__close img{width:15px}.knowledge-workspace__backdrop{display:none}
@media(max-width:1279px){.knowledge-workspace{display:block}.knowledge-workspace__folders-button{display:flex}.knowledge-workspace__backdrop{position:fixed;z-index:39;inset:0;display:block;border:0;background:rgba(20,27,37,.24)}.knowledge-workspace__inspector{position:fixed;z-index:40;top:0;right:0;bottom:0;width:min(480px,92vw);transform:translateX(105%);box-shadow:-18px 0 45px rgba(20,27,37,.18);transition:transform .2s ease}.knowledge-workspace__inspector.is-open{transform:translateX(0)}.knowledge-workspace__close{display:grid}}
@media(max-width:767px){.knowledge-workspace__header{padding:15px 12px 10px}.knowledge-workspace__title-row h1{font-size:18px}.knowledge-workspace__filters{flex-wrap:wrap}.knowledge-workspace__search{flex-basis:100%}.knowledge-workspace__filters select{flex:1}.knowledge-workspace__columns{display:none}.knowledge-workspace__row{grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:12px;min-height:104px}.knowledge-workspace__paper-cell{grid-column:1/-1}.knowledge-workspace__score{grid-column:1}.knowledge-workspace__notes,.knowledge-workspace__row time{display:none}.knowledge-workspace__status{grid-column:2;grid-row:2}.knowledge-workspace__batchbar{flex-wrap:wrap}.knowledge-workspace__batchbar strong{flex-basis:100%}.knowledge-workspace__inspector{width:100vw}.knowledge-workspace__folders-button{padding:7px 9px}}
</style>
