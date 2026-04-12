<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import {
  fetchResearchTree,
  fetchResearchSessions,
  deleteResearchSession,
  saveResearchSession,
  renameResearchSession,
  downloadResearchResult,
  moveResearchSessions,
  createKbFolder,
  renameKbFolder,
  deleteKbFolder,
} from '../../api'
import type { ResearchSession, ResearchFolder, ResearchTree } from '../../types/paper'
import KbContextMenu from '../KbContextMenu.vue'
import FolderPickerDialog from '../FolderPickerDialog.vue'
import ResearchSessionRow from './ResearchSessionRow.vue'
import type { KbMenuItem } from '../../types/paper'

const emit = defineEmits<{
  openResearchSession: [sessionId: number]
  startNewResearch: []
}>()

// ─── Data ─────────────────────────────────────────────────────
const researchTree = ref<ResearchTree>({ folders: [], sessions: [] })
const loadingResearch = ref(false)
const viewMode = ref<'history' | 'saved'>('saved')

// All sessions flattened (from tree) — used for saved view
const allSessions = computed(() => {
  const result: ResearchSession[] = []
  function collectSessions(folders: ResearchFolder[]) {
    for (const f of folders) {
      result.push(...f.sessions)
      collectSessions(f.children)
    }
  }
  collectSessions(researchTree.value.folders)
  result.push(...researchTree.value.sessions)
  return result
})

const savedSessions = computed(() => allSessions.value.filter(s => s.saved))

const filteredRootSessions = computed(() =>
  viewMode.value === 'saved'
    ? researchTree.value.sessions.filter(s => s.saved)
    : researchTree.value.sessions
)

const isEmptyView = computed(() =>
  viewMode.value === 'saved'
    ? savedSessions.value.length === 0
    : researchTree.value.folders.length === 0 && researchTree.value.sessions.length === 0
)

const totalCount = computed(() =>
  viewMode.value === 'saved'
    ? savedSessions.value.length
    : researchTree.value.folders.length + researchTree.value.sessions.length
)

async function load() {
  if (loadingResearch.value) return
  loadingResearch.value = true
  try {
    researchTree.value = await fetchResearchTree()
  } catch {
    // fallback to flat list if tree endpoint not yet deployed
    try {
      const res = await fetchResearchSessions(200)
      researchTree.value = { folders: [], sessions: res.sessions }
    } catch { /* silently ignore */ }
  } finally {
    loadingResearch.value = false
  }
}

// ─── Folder expand / active ───────────────────────────────────
const expandedFolders = ref<Set<number>>(new Set())

function toggleFolder(id: number) {
  const next = new Set(expandedFolders.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedFolders.value = next
}

// ─── Session expand ───────────────────────────────────────────
const expandedSessions = ref<Set<number>>(new Set())

function toggleExpand(id: number) {
  const next = new Set(expandedSessions.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedSessions.value = next
}

// ─── Batch mode ───────────────────────────────────────────────
const batchMode = ref(false)
const checkedSessions = ref<Set<number>>(new Set())
const hasChecked = computed(() => checkedSessions.value.size > 0)

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) checkedSessions.value = new Set()
}

function toggleCheck(id: number) {
  const next = new Set(checkedSessions.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  checkedSessions.value = next
}

// ─── Folder new / rename ──────────────────────────────────────
const showNewFolderInput = ref(false)
const newFolderName = ref('')
const newFolderParentId = ref<number | null>(null)
let _creatingFolder = false
const newFolderInputRef = ref<HTMLInputElement | null>(null)

function startNewFolder(parentId: number | null = null) {
  newFolderParentId.value = parentId
  newFolderName.value = ''
  _creatingFolder = false
  showNewFolderInput.value = true
  if (parentId !== null) {
    expandedFolders.value = new Set([...expandedFolders.value, parentId])
  }
  nextTick(() => newFolderInputRef.value?.focus())
}

async function confirmNewFolder() {
  if (_creatingFolder) return
  _creatingFolder = true
  const name = newFolderName.value.trim()
  showNewFolderInput.value = false
  if (!name) return
  try {
    await createKbFolder(name, newFolderParentId.value, 'research')
    await load()
  } catch { /* silently ignore */ }
}

function cancelNewFolder() {
  showNewFolderInput.value = false
  newFolderName.value = ''
}

const renamingFolderId = ref<number | null>(null)
const renamingFolderName = ref('')
const renameFolderInputRef = ref<HTMLInputElement | null>(null)

function startRenameFolder(folder: ResearchFolder) {
  renamingFolderId.value = folder.id
  renamingFolderName.value = folder.name
  nextTick(() => {
    renameFolderInputRef.value?.focus()
    renameFolderInputRef.value?.select()
  })
}

async function confirmRenameFolder() {
  if (renamingFolderId.value === null) return
  const id = renamingFolderId.value
  const name = renamingFolderName.value.trim()
  renamingFolderId.value = null
  if (!name) return
  try {
    await renameKbFolder(id, name, 'research')
    await load()
  } catch { /* silently ignore */ }
}

function cancelRenameFolder() {
  renamingFolderId.value = null
}

// ─── Context menu ─────────────────────────────────────────────
interface ContextMenu {
  x: number
  y: number
  items: KbMenuItem[]
  target: { type: 'folder'; folder: ResearchFolder } | { type: 'session'; session: ResearchSession }
}
const contextMenu = ref<ContextMenu | null>(null)

function openFolderMenu(e: MouseEvent, folder: ResearchFolder) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'new-subfolder', label: '新建子文件夹' },
      { key: 'rename', label: '重命名' },
      { key: 'delete', label: '删除文件夹', danger: true },
    ],
    target: { type: 'folder', folder },
  }
}

function openSessionMenu(e: MouseEvent, s: ResearchSession) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'rename', label: '重命名' },
      { key: s.saved ? 'unsave' : 'save', label: s.saved ? '取消收藏' : '收藏' },
      { key: 'move', label: '移动到文件夹...' },
      { key: 'download', label: '下载结果', disabled: s.status !== 'done' },
      { key: 'delete', label: '删除', danger: true },
    ],
    target: { type: 'session', session: s },
  }
}

async function handleMenuSelect(key: string) {
  const menu = contextMenu.value
  if (!menu) return
  contextMenu.value = null

  if (menu.target.type === 'folder') {
    const folder = menu.target.folder
    if (key === 'new-subfolder') {
      startNewFolder(folder.id)
    } else if (key === 'rename') {
      startRenameFolder(folder)
    } else if (key === 'delete') {
      await handleDeleteFolder(folder.id)
    }
  } else {
    const s = menu.target.session
    if (key === 'rename') {
      startRenameSession(s)
    } else if (key === 'save' || key === 'unsave') {
      await handleToggleSave(s)
    } else if (key === 'move') {
      movingSessionIds.value = [s.id]
      showFolderPicker.value = true
    } else if (key === 'download') {
      await handleDownload(s.id)
    } else if (key === 'delete') {
      await handleDeleteSession(s.id)
    }
  }
}

// ─── Folder delete ────────────────────────────────────────────
async function handleDeleteFolder(id: number) {
  if (!confirm('确认删除文件夹？文件夹内的研究记录将移至根目录，不会被删除。')) return
  try {
    await deleteKbFolder(id, 'research')
    await load()
  } catch { /* silently ignore */ }
}

// ─── Inline session rename ────────────────────────────────────
const renamingSessionId = ref<number | null>(null)
const renamingSessionText = ref('')

function startRenameSession(s: ResearchSession) {
  renamingSessionId.value = s.id
  renamingSessionText.value = s.question
}

async function confirmRenameSession() {
  if (renamingSessionId.value === null) return
  const id = renamingSessionId.value
  const text = renamingSessionText.value.trim()
  renamingSessionId.value = null
  if (!text) return
  try {
    await renameResearchSession(id, text)
    await load()
  } catch { /* silently ignore */ }
}

function cancelRenameSession() {
  renamingSessionId.value = null
}

// ─── Save / unsave ────────────────────────────────────────────
async function handleToggleSave(s: ResearchSession) {
  try {
    await saveResearchSession(s.id, !s.saved)
    await load()
  } catch { /* silently ignore */ }
}

// ─── Download ─────────────────────────────────────────────────
async function handleDownload(id: number) {
  try {
    await downloadResearchResult(id, 'md')
  } catch { /* silently ignore */ }
}

// ─── Delete session ───────────────────────────────────────────
async function handleDeleteSession(id: number) {
  if (!confirm('确认删除这条研究记录？删除后无法恢复。')) return
  try {
    await deleteResearchSession(id)
    expandedSessions.value = new Set([...expandedSessions.value].filter(x => x !== id))
    checkedSessions.value = new Set([...checkedSessions.value].filter(x => x !== id))
    await load()
  } catch { /* silently ignore */ }
}

// ─── Folder picker (move sessions) ───────────────────────────
const showFolderPicker = ref(false)
const movingSessionIds = ref<number[]>([])

async function handleFolderPickerSelect(targetFolderId: number | null) {
  showFolderPicker.value = false
  if (movingSessionIds.value.length === 0) return
  try {
    await moveResearchSessions(movingSessionIds.value, targetFolderId)
    checkedSessions.value = new Set()
    await load()
  } catch { /* silently ignore */ }
  movingSessionIds.value = []
}

// ─── Batch actions ────────────────────────────────────────────
async function batchToggleSave() {
  const ids = [...checkedSessions.value]
  const sessions = allSessions.value.filter(s => ids.includes(s.id))
  const newVal = sessions.some(s => !s.saved)
  await Promise.allSettled(ids.map(id => saveResearchSession(id, newVal)))
  await load()
}

async function batchDownload() {
  const ids = [...checkedSessions.value]
  const done = allSessions.value.filter(s => ids.includes(s.id) && s.status === 'done')
  await Promise.allSettled(done.map(s => downloadResearchResult(s.id, 'md')))
}

async function batchDelete() {
  const ids = [...checkedSessions.value]
  if (!confirm(`确认删除选中的 ${ids.length} 条研究记录？删除后无法恢复。`)) return
  await Promise.allSettled(ids.map(id => deleteResearchSession(id)))
  expandedSessions.value = new Set([...expandedSessions.value].filter(x => !ids.includes(x)))
  checkedSessions.value = new Set()
  await load()
}

function batchMove() {
  movingSessionIds.value = [...checkedSessions.value]
  showFolderPicker.value = true
}

function switchToSaved() {
  viewMode.value = 'saved'
}

onMounted(load)

defineExpose({ load, switchToSaved })
</script>

<template>
  <div
    class="flex-1 flex flex-col min-h-0 overflow-hidden"
    @click="contextMenu = null"
  >

    <!-- Header with toolbar -->
    <div class="px-3 pt-3 pb-2 border-b border-border shrink-0">
      <!-- Title row -->
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v11m0 0H5a2 2 0 0 1-2-2V7m6 7h10m0 0a2 2 0 0 0 2-2V7m-12 7v4m0 0h4m-4 0H5"/>
            <circle cx="17" cy="18" r="3"/><path d="m21 22-1.5-1.5"/>
          </svg>
          <span class="text-xs font-semibold text-text-primary">深度研究</span>
        </div>
        <button
          class="text-[11px] text-text-muted hover:text-accent-primary transition-colors px-2 py-1 rounded-lg hover:bg-bg-elevated cursor-pointer border-none bg-transparent"
          :disabled="loadingResearch"
          @click.stop="load"
        >刷新</button>
      </div>

      <!-- Toolbar row: count + batch + new folder -->
      <div class="flex items-center justify-between">
        <span class="text-[11px] text-text-muted/50 select-none">
          <template v-if="totalCount > 0">{{ totalCount }} 条</template>
          <template v-else>深度研究</template>
        </span>
        <div class="flex items-center gap-1.5">
          <button
            class="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-transparent border cursor-pointer transition-colors"
            :class="batchMode
              ? 'border-tinder-pink/60 text-tinder-pink bg-tinder-pink/5'
              : 'border-border text-text-muted hover:text-text-secondary hover:border-border-light'"
            title="批量选择，可批量收藏、移动、下载或删除"
            @click.stop="toggleBatchMode"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="5" width="4" height="4" rx="1"/><rect x="3" y="11" width="4" height="4" rx="1"/><rect x="3" y="17" width="4" height="4" rx="1"/><line x1="10" y1="7" x2="21" y2="7"/><line x1="10" y1="13" x2="21" y2="13"/><line x1="10" y1="19" x2="21" y2="19"/>
            </svg>
            批量
          </button>
          <button
            class="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-transparent border border-border text-text-muted hover:text-tinder-pink hover:border-tinder-pink/40 cursor-pointer transition-colors"
            title="新建文件夹"
            @click.stop="startNewFolder(null)"
          >
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
            </svg>
            新建
          </button>
        </div>
      </div>
    </div>

    <!-- CTA button to start research -->
    <div class="px-3 pt-2 pb-1 shrink-0">
      <button
        class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-[#0ea5e9] to-[#6366f1] border-none cursor-pointer hover:opacity-90 transition-opacity"
        @click.stop="emit('startNewResearch')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>
        </svg>
        发起深度研究
      </button>
    </div>

    <!-- History | Saved filter toggle -->
    <div class="px-3 pb-2 shrink-0">
      <div class="flex rounded-lg overflow-hidden border border-border bg-bg-elevated text-xs font-medium">
        <button
          class="flex-1 py-1.5 transition-colors border-none cursor-pointer"
          :class="viewMode === 'saved'
            ? 'bg-accent-primary/15 text-accent-primary'
            : 'bg-transparent text-text-muted hover:text-text-primary hover:bg-bg-hover'"
          @click.stop="viewMode = 'saved'"
        >收藏</button>
        <div class="w-px bg-border shrink-0"></div>
        <button
          class="flex-1 py-1.5 transition-colors border-none cursor-pointer"
          :class="viewMode === 'history'
            ? 'bg-accent-primary/15 text-accent-primary'
            : 'bg-transparent text-text-muted hover:text-text-primary hover:bg-bg-hover'"
          @click.stop="viewMode = 'history'"
        >历史</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loadingResearch" class="flex items-center justify-center gap-2 py-10 text-xs text-text-muted">
      <svg class="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      加载中…
    </div>

    <!-- Empty state -->
    <div v-else-if="isEmptyView" class="flex flex-col items-center justify-center flex-1 py-10 px-4 text-center text-text-muted">
      <svg v-if="viewMode === 'saved'" class="w-8 h-8 mb-3 opacity-25" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
      </svg>
      <svg v-else class="w-8 h-8 mb-3 opacity-25" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v11m0 0H5a2 2 0 0 1-2-2V7m6 7h10m0 0a2 2 0 0 0 2-2V7m-12 7v4m0 0h4m-4 0H5"/>
        <circle cx="17" cy="18" r="3"/><path d="m21 22-1.5-1.5"/>
      </svg>
      <p class="text-sm font-medium mb-1">{{ viewMode === 'saved' ? '暂无收藏' : '暂无研究记录' }}</p>
      <p class="text-[11px] leading-relaxed text-text-muted/70">
        {{ viewMode === 'saved' ? '研究完成后点击「保存到研究库」即可收藏。' : '选中论文后点击「深度研究」，结果会保存在这里。' }}
      </p>
    </div>

    <!-- Main list (history or saved) -->
    <div v-else class="flex-1 overflow-y-auto py-1">

      <!-- New folder input (root level) -->
      <div v-if="showNewFolderInput && newFolderParentId === null" class="flex items-center gap-2 px-2 py-2 mx-1 mb-1">
        <svg class="shrink-0 text-text-muted" style="width:18px;height:18px;"
             viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <input
          ref="newFolderInputRef"
          v-model="newFolderName"
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent-primary/50"
          placeholder="文件夹名称..."
          @keydown.enter.prevent="confirmNewFolder"
          @keydown.escape.prevent="cancelNewFolder"
          @blur="confirmNewFolder"
          @click.stop
        />
      </div>

      <!-- Folders (history view only) -->
      <template v-if="viewMode === 'history'">
        <div
          v-for="folder in researchTree.folders"
          :key="folder.id"
          class="mb-0.5"
        >
          <!-- Folder row -->
          <div
            class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors group cursor-pointer"
            @click.stop="toggleFolder(folder.id)"
          >
            <!-- Expand arrow (SVG chevron) -->
            <svg
              class="w-3 h-3 shrink-0 text-text-muted transition-transform duration-150"
              :class="expandedFolders.has(folder.id) ? 'rotate-90' : ''"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="9 18 15 12 9 6"/>
            </svg>

            <!-- Folder icon (stroke-only, text-secondary) -->
            <svg class="shrink-0 text-text-secondary" style="width:18px;height:18px;"
                 viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>

            <!-- Name or rename input -->
            <div class="flex-1 min-w-0" @click.stop>
              <input
                v-if="renamingFolderId === folder.id"
                ref="renameFolderInputRef"
                v-model="renamingFolderName"
                class="w-full bg-bg-elevated border border-accent-primary/50 rounded px-1.5 py-0.5 text-xs text-text-primary focus:outline-none focus:border-accent-primary"
                @keydown.enter.prevent="confirmRenameFolder"
                @keydown.escape.prevent="cancelRenameFolder"
                @blur="confirmRenameFolder"
                @click.stop
              />
              <span v-else class="text-xs font-semibold text-text-primary truncate block">{{ folder.name }}</span>
            </div>

            <!-- Session count badge -->
            <span v-if="folder.sessions.length > 0 && renamingFolderId !== folder.id" class="text-[10px] text-text-muted shrink-0">{{ folder.sessions.length }}</span>

            <!-- Menu button -->
            <button
              v-if="renamingFolderId !== folder.id"
              class="w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded-lg opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
              @click.stop="openFolderMenu($event, folder)"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5">
                <circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>
              </svg>
            </button>
          </div>

          <!-- New subfolder input -->
          <div v-if="showNewFolderInput && newFolderParentId === folder.id" class="flex items-center gap-2 pl-8 pr-2 py-1.5">
            <svg class="shrink-0 text-text-muted" style="width:18px;height:18px;"
                 viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <input
              ref="newFolderInputRef"
              v-model="newFolderName"
              class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent-primary/50"
              placeholder="子文件夹名称..."
              @keydown.enter.prevent="confirmNewFolder"
              @keydown.escape.prevent="cancelNewFolder"
              @blur="confirmNewFolder"
              @click.stop
            />
          </div>

          <!-- Folder sessions (expanded) -->
          <div v-if="expandedFolders.has(folder.id)">
            <div v-if="folder.sessions.length === 0" class="pl-8 pr-2 py-2 text-[11px] text-text-muted/60">暂无研究记录</div>
            <ResearchSessionRow
              v-for="s in folder.sessions"
              :key="s.id"
              :session="s"
              :batch-mode="batchMode"
              :checked="checkedSessions.has(s.id)"
              :expanded="expandedSessions.has(s.id)"
              :renaming-id="renamingSessionId"
              :renaming-text="renamingSessionText"
              :indent="true"
              @open="emit('openResearchSession', s.id)"
              @toggle-check="toggleCheck(s.id)"
              @toggle-expand="toggleExpand(s.id)"
              @open-menu="openSessionMenu($event, s)"
              @update:renaming-text="renamingSessionText = $event"
              @confirm-rename="confirmRenameSession"
              @cancel-rename="cancelRenameSession"
            />
          </div>
        </div>

        <!-- Root sessions (history view) -->
        <ResearchSessionRow
          v-for="s in filteredRootSessions"
          :key="s.id"
          :session="s"
          :batch-mode="batchMode"
          :checked="checkedSessions.has(s.id)"
          :expanded="expandedSessions.has(s.id)"
          :renaming-id="renamingSessionId"
          :renaming-text="renamingSessionText"
          :indent="false"
          @open="emit('openResearchSession', s.id)"
          @toggle-check="toggleCheck(s.id)"
          @toggle-expand="toggleExpand(s.id)"
          @open-menu="openSessionMenu($event, s)"
          @update:renaming-text="renamingSessionText = $event"
          @confirm-rename="confirmRenameSession"
          @cancel-rename="cancelRenameSession"
        />
      </template>

      <!-- Saved view: flat list of all saved sessions -->
      <template v-else>
        <ResearchSessionRow
          v-for="s in savedSessions"
          :key="s.id"
          :session="s"
          :batch-mode="batchMode"
          :checked="checkedSessions.has(s.id)"
          :expanded="expandedSessions.has(s.id)"
          :renaming-id="renamingSessionId"
          :renaming-text="renamingSessionText"
          :indent="false"
          @open="emit('openResearchSession', s.id)"
          @toggle-check="toggleCheck(s.id)"
          @toggle-expand="toggleExpand(s.id)"
          @open-menu="openSessionMenu($event, s)"
          @update:renaming-text="renamingSessionText = $event"
          @confirm-rename="confirmRenameSession"
          @cancel-rename="cancelRenameSession"
        />
      </template>

    </div>

    <!-- Batch action bar -->
    <div
      v-if="batchMode"
      class="px-3 py-2.5 border-t border-border bg-bg-elevated flex flex-col gap-2 shrink-0"
    >
      <div class="flex items-center justify-between">
        <span class="text-xs text-text-muted">已选 {{ checkedSessions.size }} 条</span>
        <button
          class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="toggleBatchMode"
        >取消</button>
      </div>
      <div class="flex items-center gap-2">
        <button
          :disabled="!hasChecked"
          class="flex-1 px-2 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="hasChecked ? 'text-white bg-brand-gradient hover:opacity-90' : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          title="移动到文件夹"
          @click="batchMove"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          移动
        </button>
        <button
          :disabled="!hasChecked"
          class="flex-1 px-2 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="hasChecked ? 'text-white bg-gradient-to-r from-amber-400 to-orange-400 hover:opacity-90' : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          title="批量收藏/取消收藏"
          @click="batchToggleSave"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="currentColor" stroke="none">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          收藏
        </button>
        <button
          :disabled="!hasChecked"
          class="flex-1 px-2 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="hasChecked ? 'text-white bg-gradient-to-r from-[#10b981] to-[#059669] hover:opacity-90' : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          title="批量下载已完成的研究结果（MD 格式）"
          @click="batchDownload"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载
        </button>
        <button
          :disabled="!hasChecked"
          class="flex-1 px-2 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="hasChecked ? 'text-tinder-pink bg-tinder-pink/10 hover:bg-tinder-pink/20' : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          title="批量删除选中记录"
          @click="batchDelete"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
          </svg>
          删除
        </button>
      </div>
    </div>

    <!-- Context menu -->
    <KbContextMenu
      v-if="contextMenu"
      :items="contextMenu.items"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @select="handleMenuSelect"
      @close="contextMenu = null"
    />

    <!-- Folder picker dialog -->
    <FolderPickerDialog
      v-if="showFolderPicker"
      :folders="researchTree.folders"
      title="移动研究记录到文件夹"
      @select="handleFolderPickerSelect"
      @cancel="showFolderPicker = false"
    />

  </div>
</template>
