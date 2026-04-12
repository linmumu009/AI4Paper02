<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import PaperListItem from '@/components/PaperListItem.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import {
  fetchKbTree,
  createKbFolder,
  renameKbFolder,
  deleteKbFolder,
  removeKbPaper,
  moveKbPapers,
  updateKbPaperReadStatus,
  renameKbPaper,
} from '@shared/api'
import { fetchKbPaperProcessStatus, kbPaperStepLabel } from '@shared/api/kb-processing'
import type { KbTree, KbFolder, KbPaper } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'KnowledgeView' })

const router = useRouter()

const tree = ref<KbTree | null>(null)
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')

// Expanded folder ids
const expandedFolders = ref<Set<number>>(new Set())

// Action sheet state
const actionSheetVisible = ref(false)
const actionTarget = ref<{ type: 'folder' | 'paper'; item: KbFolder | KbPaper } | null>(null)

// New folder sheet
const newFolderVisible = ref(false)
const newFolderName = ref('')
const newFolderParentId = ref<number | null>(null)
const savingFolder = ref(false)

// Rename sheet
const renameVisible = ref(false)
const renameName = ref('')

// Move sheet
const moveSheetVisible = ref(false)
const movingPaperId = ref<string | null>(null)

// Paper rename sheet
const paperRenameVisible = ref(false)
const paperRenameName = ref('')

// Batch mode
const batchMode = ref(false)
const selectedPaperIds = ref(new Set<string>())
const batchMoving = ref(false)
const batchDeleting = ref(false)
const batchMoveSheetVisible = ref(false)

// Process status sheet
const processStatusVisible = ref(false)
const processStatusPaper = ref<KbPaper | null>(null)
const processStatusData = ref<{ process_status: string; process_step: string; process_error: string } | null>(null)
const loadingProcessStatus = ref(false)

async function loadTree() {
  loading.value = true
  error.value = ''
  try {
    tree.value = await fetchKbTree('kb')
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function showProcessStatus(paper: KbPaper) {
  processStatusPaper.value = paper
  processStatusVisible.value = true
  processStatusData.value = null
  loadingProcessStatus.value = true
  try {
    const res = await fetchKbPaperProcessStatus(paper.paper_id)
    processStatusData.value = res
  } catch { /* best-effort */ }
  loadingProcessStatus.value = false
}

function onPaperClick(paper: KbPaper) {
  if (paper.process_status === 'processing' || paper.process_status === 'pending') {
    showProcessStatus(paper)
  } else {
    router.push(`/paper/${paper.paper_id}`)
  }
}

onMounted(loadTree)

// Flatten all papers (for search)
const allPapers = computed<Array<{ paper: KbPaper; folderName: string | null }>>(() => {
  if (!tree.value) return []
  const result: Array<{ paper: KbPaper; folderName: string | null }> = []
  // Root papers
  for (const p of tree.value.papers) {
    result.push({ paper: p, folderName: null })
  }
  // Folder papers (recursive)
  function collectFolder(folder: KbFolder) {
    for (const p of folder.papers) {
      result.push({ paper: p, folderName: folder.name })
    }
    for (const child of folder.children) {
      collectFolder(child)
    }
  }
  for (const f of tree.value.folders) {
    collectFolder(f)
  }
  return result
})

const filteredPapers = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []
  return allPapers.value.filter(({ paper }) => {
    const title = (paper.paper_data?.short_title || paper.paper_data?.['📖标题'] || paper.paper_id).toLowerCase()
    const inst = (paper.paper_data?.institution || '').toLowerCase()
    return title.includes(q) || inst.includes(q)
  })
})

const totalCount = computed(() => allPapers.value.length)

function toggleFolder(id: number) {
  if (expandedFolders.value.has(id)) {
    expandedFolders.value.delete(id)
  } else {
    expandedFolders.value.add(id)
  }
}

function onPaperLongPress(paper: KbPaper) {
  actionTarget.value = { type: 'paper', item: paper }
  actionSheetVisible.value = true
}

function onFolderLongPress(folder: KbFolder) {
  actionTarget.value = { type: 'folder', item: folder }
  actionSheetVisible.value = true
}

function openNewFolder(parentId: number | null = null) {
  newFolderParentId.value = parentId
  newFolderName.value = ''
  newFolderVisible.value = true
}

async function confirmNewFolder() {
  if (!newFolderName.value.trim()) return
  savingFolder.value = true
  try {
    await createKbFolder(newFolderName.value.trim(), newFolderParentId.value, 'kb')
    newFolderVisible.value = false
    await loadTree()
    showToast('文件夹已创建')
  } catch {
    showToast('创建失败，请重试')
  } finally {
    savingFolder.value = false
  }
}

async function handleActionSheetItem(action: string) {
  actionSheetVisible.value = false
  const target = actionTarget.value
  if (!target) return

  if (target.type === 'folder') {
    const folder = target.item as KbFolder
    if (action === 'rename') {
      renameName.value = folder.name
      renameVisible.value = true
    } else if (action === 'new-sub') {
      openNewFolder(folder.id)
    } else if (action === 'delete') {
      try {
        await showDialog({
          title: '删除文件夹',
          message: `确定删除「${folder.name}」？文件夹内的论文将移到未分类。`,
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          confirmButtonColor: 'var(--color-tinder-pink)',
        })
        await deleteKbFolder(folder.id, 'kb')
        await loadTree()
        showToast('已删除')
      } catch {
        // user cancelled
      }
    }
  } else {
    const paper = target.item as KbPaper
    if (action === 'ai-chat') {
      const title = paper.paper_data?.short_title || paper.paper_data?.['📖标题'] || paper.paper_id
      router.push({ name: 'chat', query: { paperId: paper.paper_id, title } })
    } else if (action === 'move') {
      movingPaperId.value = paper.paper_id
      moveSheetVisible.value = true
    } else if (action === 'rename') {
      paperRenameName.value = paper.paper_data?.short_title || paper.paper_data?.['📖标题'] || paper.paper_id
      renameVisible.value = true
    } else if (action === 'read-unread') {
      await setReadStatus(paper, 'unread')
    } else if (action === 'read-reading') {
      await setReadStatus(paper, 'reading')
    } else if (action === 'read-read') {
      await setReadStatus(paper, 'read')
    } else if (action === 'delete') {
      try {
        await showDialog({
          title: '从知识库移除',
          message: '确定从知识库移除这篇论文？',
          confirmButtonText: '移除',
          cancelButtonText: '取消',
          confirmButtonColor: 'var(--color-tinder-pink)',
        })
        await removeKbPaper(paper.paper_id, 'kb')
        await loadTree()
        showToast('已移除')
      } catch {
        // user cancelled
      }
    }
  }
}

async function setReadStatus(paper: KbPaper, status: 'unread' | 'reading' | 'read') {
  try {
    await updateKbPaperReadStatus(paper.paper_id, status)
    // Update local tree state without full reload
    paper.read_status = status
    showToast(status === 'unread' ? '已标记未读' : status === 'reading' ? '已标记阅读中' : '已标记已读')
  } catch {
    showToast('操作失败')
  }
}

async function confirmRename() {
  const target = actionTarget.value
  if (!target) return
  if (target.type === 'folder') {
    const folder = target.item as KbFolder
    if (!renameName.value.trim()) return
    try {
      await renameKbFolder(folder.id, renameName.value.trim(), 'kb')
      renameVisible.value = false
      await loadTree()
      showToast('已重命名')
    } catch {
      showToast('操作失败')
    }
  } else {
    const paper = target.item as KbPaper
    if (!paperRenameName.value.trim()) return
    try {
      await renameKbPaper(paper.paper_id, paperRenameName.value.trim(), 'kb')
      renameVisible.value = false
      // Update locally
      if (paper.paper_data) paper.paper_data.short_title = paperRenameName.value.trim()
      showToast('已重命名')
    } catch {
      showToast('操作失败')
    }
  }
}

// Collect all folders for move target
const allFolders = computed<KbFolder[]>(() => {
  if (!tree.value) return []
  const result: KbFolder[] = []
  function collect(folders: KbFolder[]) {
    for (const f of folders) {
      result.push(f)
      collect(f.children)
    }
  }
  collect(tree.value.folders)
  return result
})

async function movePaperToFolder(folderId: number | null) {
  if (!movingPaperId.value) return
  moveSheetVisible.value = false
  try {
    await moveKbPapers([movingPaperId.value], folderId, 'kb')
    await loadTree()
    showToast('已移动')
  } catch {
    showToast('移动失败')
  } finally {
    movingPaperId.value = null
  }
}

// Batch operations
function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) selectedPaperIds.value.clear()
}

function toggleSelectPaper(paper: KbPaper) {
  if (selectedPaperIds.value.has(paper.paper_id)) selectedPaperIds.value.delete(paper.paper_id)
  else selectedPaperIds.value.add(paper.paper_id)
}

function selectAll() {
  const all = allPapers.value.map((p) => p.paper.paper_id)
  if (selectedPaperIds.value.size === all.length) selectedPaperIds.value.clear()
  else all.forEach((id) => selectedPaperIds.value.add(id))
}

async function batchDeleteSelected() {
  if (selectedPaperIds.value.size === 0) return
  try {
    await showDialog({ title: '批量移除', message: `确定从知识库移除选中的 ${selectedPaperIds.value.size} 篇论文？`, confirmButtonText: '移除', cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    batchDeleting.value = true
    for (const pid of selectedPaperIds.value) {
      await removeKbPaper(pid, 'kb').catch(() => {/* best-effort */})
    }
    selectedPaperIds.value.clear()
    batchMode.value = false
    await loadTree()
    showToast('已移除')
  } catch { /* cancelled */ } finally { batchDeleting.value = false }
}

async function batchMoveToFolder(folderId: number | null) {
  if (selectedPaperIds.value.size === 0) return
  batchMoveSheetVisible.value = false
  batchMoving.value = true
  try {
    await moveKbPapers([...selectedPaperIds.value], folderId, 'kb')
    selectedPaperIds.value.clear()
    batchMode.value = false
    await loadTree()
    showToast('已移动')
  } catch { showToast('移动失败') } finally { batchMoving.value = false }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader title="知识库">
      <template #right>
        <button
          type="button"
          class="px-3 h-7 rounded-full text-[12px] font-semibold border transition-colors mr-1"
          :class="batchMode ? 'border-tinder-pink bg-tinder-pink/10 text-tinder-pink' : 'border-border text-text-muted'"
          @click="toggleBatchMode"
        >
          {{ batchMode ? '完成' : '管理' }}
        </button>
        <button
          v-if="!batchMode"
          type="button"
          class="top-nav-btn"
          aria-label="自动分类设置"
          @click="router.push('/knowledge/auto-classify')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
        <button
          v-if="!batchMode"
          type="button"
          class="top-nav-btn"
          aria-label="新建文件夹"
          @click="openNewFolder(null)"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            <line x1="12" y1="11" x2="12" y2="17" />
            <line x1="9" y1="14" x2="15" y2="14" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <!-- Search bar -->
    <div class="px-4 pb-3 shrink-0">
      <SearchBar v-model="searchQuery" placeholder="搜索论文标题、机构…" />
    </div>

    <!-- Loading -->
    <LoadingState v-if="loading" class="flex-1" message="加载知识库…" />

    <!-- Error -->
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadTree" />

    <!-- Search results -->
    <div v-else-if="searchQuery.trim()" class="flex-1 overflow-y-auto">
      <div v-if="filteredPapers.length === 0" class="flex flex-col items-center justify-center h-48 text-text-muted">
        <p class="text-sm">未找到匹配的论文</p>
      </div>
      <template v-else>
        <p class="px-4 py-2 text-[12px] text-text-muted">找到 {{ filteredPapers.length }} 篇论文</p>
        <PaperListItem
          v-for="{ paper, folderName } in filteredPapers"
          :key="paper.paper_id"
          :paper="paper"
          :show-folder="true"
          :folder-name="folderName ?? undefined"
          :batch-mode="batchMode"
          :selected="selectedPaperIds.has(paper.paper_id)"
          @click="onPaperClick(paper)"
          @longpress="onPaperLongPress(paper)"
          @toggle-select="toggleSelectPaper(paper)"
        />
      </template>
    </div>

    <!-- Tree view -->
    <div v-else-if="tree" class="flex-1 overflow-y-auto">
      <!-- Stats row -->
      <div class="px-4 py-2 flex items-center justify-between">
        <span class="text-[12px] text-text-muted">{{ totalCount }} 篇论文</span>
      </div>

      <!-- Empty state -->
      <EmptyState
        v-if="totalCount === 0"
        title="知识库还是空的"
        description="在推荐页收藏论文后，它们会出现在这里"
      />

      <template v-else>
        <!-- Folders (always first) -->
        <template v-if="tree.folders.length > 0">
          <div class="px-4 pt-2 pb-2 text-[11px] font-semibold text-text-muted uppercase tracking-wider">文件夹</div>

          <!-- Folder grid -->
          <div class="px-4 pb-1 grid grid-cols-2 gap-2.5">
            <div
              v-for="folder in tree.folders"
              :key="folder.id"
              class="relative rounded-2xl bg-bg-card overflow-hidden active:opacity-75 transition-opacity cursor-pointer"
              style="min-height: 84px;"
              @click="toggleFolder(folder.id)"
            >
              <!-- Three-dot menu — top-right -->
              <button
                type="button"
                class="absolute top-0 right-0 w-[44px] h-[44px] flex items-center justify-center text-text-muted active:text-text-primary z-10"
                aria-label="文件夹操作"
                @click.stop="onFolderLongPress(folder)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="1.8" />
                  <circle cx="12" cy="12" r="1.8" />
                  <circle cx="12" cy="19" r="1.8" />
                </svg>
              </button>

              <!-- Card body -->
              <div class="px-3.5 pt-3 pb-3 flex flex-col gap-2 h-full">
                <!-- Icon block -->
                <div class="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style="background: rgba(245,183,49,0.13);">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <path d="M3 7C3 5.9 3.9 5 5 5h4.17L10.59 6.41C10.96 6.78 11.46 7 11.99 7H19c1.1 0 2 .9 2 2v10c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V7z" fill="#f5b731" opacity="0.25"/>
                    <path d="M3 9C3 7.9 3.9 7 5 7h14c1.1 0 2 .9 2 2v9c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9z" fill="#f5b731"/>
                  </svg>
                </div>

                <!-- Name + count row -->
                <div class="flex items-end justify-between gap-1 pr-6">
                  <div class="min-w-0">
                    <p class="text-[13px] font-semibold text-text-primary truncate leading-tight">{{ folder.name }}</p>
                    <p class="text-[11px] text-text-muted mt-0.5 tabular-nums">
                      {{ folder.papers.length + folder.children.reduce((a, c) => a + c.papers.length, 0) }} 篇
                    </p>
                  </div>
                  <!-- Chevron -->
                  <svg
                    class="shrink-0 text-text-muted transition-transform mb-0.5"
                    :class="expandedFolders.has(folder.id) ? 'rotate-90' : ''"
                    width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </div>
              </div>
            </div>
          </div>

          <!-- Expanded folder content — rendered below the grid, full-width -->
          <template v-for="folder in tree.folders" :key="`expand-${folder.id}`">
            <div v-if="expandedFolders.has(folder.id)" class="mt-2 mb-1 mx-4 rounded-2xl bg-bg-card overflow-hidden">
              <!-- Expand header -->
              <div class="flex items-center gap-2 px-4 py-2.5 border-b border-border/60">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" class="text-tinder-gold shrink-0">
                  <path d="M3 9C3 7.9 3.9 7 5 7h14c1.1 0 2 .9 2 2v9c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9z"/>
                </svg>
                <span class="text-[12px] font-semibold text-text-secondary truncate flex-1">{{ folder.name }}</span>
                <button
                  type="button"
                  class="text-[11px] text-text-muted active:text-text-primary px-1 py-0.5"
                  @click="toggleFolder(folder.id)"
                >
                  收起
                </button>
              </div>

              <!-- Sub-folders -->
              <div v-for="sub in folder.children" :key="sub.id">
                <button
                  type="button"
                  class="w-full flex items-center gap-3 pl-4 pr-4 py-3 active:bg-bg-hover transition-colors border-b border-border/40 min-h-[44px]"
                  @click="toggleFolder(sub.id)"
                >
                  <div class="shrink-0 text-tinder-gold opacity-60">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M3 9C3 7.9 3.9 7 5 7h14c1.1 0 2 .9 2 2v9c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9z"/>
                    </svg>
                  </div>
                  <span class="flex-1 text-left text-[13px] text-text-secondary">{{ sub.name }}</span>
                  <span class="text-[11px] text-text-muted tabular-nums mr-1">{{ sub.papers.length }} 篇</span>
                  <svg
                    class="shrink-0 text-text-muted transition-transform"
                    :class="expandedFolders.has(sub.id) ? 'rotate-90' : ''"
                    width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
                <div v-if="expandedFolders.has(sub.id)" class="bg-bg/40">
                  <PaperListItem
                    v-for="paper in sub.papers"
                    :key="paper.paper_id"
                    :paper="paper"
                    :batch-mode="batchMode"
                    :selected="selectedPaperIds.has(paper.paper_id)"
                    @click="onPaperClick(paper)"
                    @longpress="onPaperLongPress(paper)"
                    @toggle-select="toggleSelectPaper(paper)"
                  />
                  <div v-if="sub.papers.length === 0" class="px-4 py-3 text-[12px] text-text-muted">此文件夹为空</div>
                </div>
              </div>

              <!-- Papers in folder -->
              <PaperListItem
                v-for="paper in folder.papers"
                :key="paper.paper_id"
                :paper="paper"
                :batch-mode="batchMode"
                :selected="selectedPaperIds.has(paper.paper_id)"
                @click="onPaperClick(paper)"
                @longpress="onPaperLongPress(paper)"
                @toggle-select="toggleSelectPaper(paper)"
              />
              <div v-if="folder.papers.length === 0 && folder.children.length === 0" class="px-4 py-4 text-[12px] text-text-muted text-center">
                此文件夹为空
              </div>
            </div>
          </template>
        </template>

        <!-- Root papers (no folder) — shown after folders -->
        <div v-if="tree.papers.length > 0">
          <div class="px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-wider">未分类</div>
          <PaperListItem
            v-for="paper in tree.papers"
            :key="paper.paper_id"
            :paper="paper"
            :batch-mode="batchMode"
            :selected="selectedPaperIds.has(paper.paper_id)"
            @click="onPaperClick(paper)"
            @longpress="onPaperLongPress(paper)"
            @toggle-select="toggleSelectPaper(paper)"
          />
        </div>
      </template>
    </div>

    <!-- ── Action Sheet: folder/paper operations ── -->
    <BottomSheet
      :visible="actionSheetVisible"
      :title="actionTarget?.type === 'folder' ? (actionTarget.item as KbFolder).name : '论文操作'"
      @close="actionSheetVisible = false"
    >
      <div class="pb-2">
        <template v-if="actionTarget?.type === 'folder'">
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-text-primary active:bg-bg-hover"
            @click="handleActionSheetItem('rename')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            重命名
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-text-primary active:bg-bg-hover"
            @click="handleActionSheetItem('new-sub')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /><line x1="12" y1="11" x2="12" y2="17" /><line x1="9" y1="14" x2="15" y2="14" /></svg>
            新建子文件夹
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-tinder-pink active:bg-bg-hover"
            @click="handleActionSheetItem('delete')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
            删除文件夹
          </button>
        </template>
        <template v-else-if="actionTarget?.type === 'paper'">
          <!-- Read status -->
          <div class="px-5 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-wider">标记状态</div>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-3.5 text-[15px] active:bg-bg-hover"
            :class="(actionTarget.item as KbPaper).read_status === 'unread' || !(actionTarget.item as KbPaper).read_status ? 'text-tinder-blue' : 'text-text-primary'"
            @click="handleActionSheetItem('read-unread')"
          >
            <span class="w-4.5 h-4.5 shrink-0 inline-flex items-center justify-center">
              <span class="w-2 h-2 rounded-full bg-tinder-blue" />
            </span>
            未读
            <svg v-if="(actionTarget.item as KbPaper).read_status === 'unread' || !(actionTarget.item as KbPaper).read_status" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-blue ml-auto"><polyline points="20 6 9 17 4 12" /></svg>
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-3.5 text-[15px] active:bg-bg-hover"
            :class="(actionTarget.item as KbPaper).read_status === 'reading' ? 'text-tinder-gold' : 'text-text-primary'"
            @click="handleActionSheetItem('read-reading')"
          >
            <span class="w-4.5 h-4.5 shrink-0 inline-flex items-center justify-center">
              <span class="w-2 h-2 rounded-full bg-tinder-gold" />
            </span>
            阅读中
            <svg v-if="(actionTarget.item as KbPaper).read_status === 'reading'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-gold ml-auto"><polyline points="20 6 9 17 4 12" /></svg>
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-3.5 text-[15px] active:bg-bg-hover"
            :class="(actionTarget.item as KbPaper).read_status === 'read' ? 'text-tinder-green' : 'text-text-primary'"
            @click="handleActionSheetItem('read-read')"
          >
            <span class="w-4.5 h-4.5 shrink-0 inline-flex items-center justify-center">
              <span class="w-2 h-2 rounded-full bg-text-muted opacity-50" />
            </span>
            已读
            <svg v-if="(actionTarget.item as KbPaper).read_status === 'read'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-green ml-auto"><polyline points="20 6 9 17 4 12" /></svg>
          </button>
          <div class="h-px bg-border mx-5 my-1" />
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 active:bg-bg-hover text-left"
            @click="handleActionSheetItem('ai-chat')"
          >
            <div class="w-9 h-9 rounded-xl bg-tinder-purple/10 flex items-center justify-center shrink-0">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-purple">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[14px] font-medium text-text-primary">AI 对话</p>
              <p class="text-[12px] text-text-muted mt-0.5">与 AI 讨论这篇论文</p>
            </div>
          </button>
          <div class="h-px bg-border mx-5 my-1" />
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-text-primary active:bg-bg-hover"
            @click="handleActionSheetItem('move')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="5 9 2 12 5 15" /><polyline points="9 5 12 2 15 5" /><polyline points="15 19 12 22 9 19" /><polyline points="19 9 22 12 19 15" /><line x1="2" y1="12" x2="22" y2="12" /></svg>
            移动到文件夹
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-text-primary active:bg-bg-hover"
            @click="handleActionSheetItem('rename')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            重命名论文
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-tinder-pink active:bg-bg-hover"
            @click="handleActionSheetItem('delete')"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
            从知识库移除
          </button>
        </template>
      </div>
    </BottomSheet>

    <!-- ── New Folder Sheet ── -->
    <BottomSheet
      :visible="newFolderVisible"
      title="新建文件夹"
      @close="newFolderVisible = false"
    >
      <div class="px-5 pb-5 pt-2 flex flex-col gap-4">
        <input
          v-model="newFolderName"
          type="text"
          placeholder="文件夹名称"
          class="input-field"
          maxlength="40"
          @keyup.enter="confirmNewFolder"
        />
        <button
          type="button"
          class="btn-primary"
          :disabled="!newFolderName.trim() || savingFolder"
          @click="confirmNewFolder"
        >
          {{ savingFolder ? '创建中…' : '创建' }}
        </button>
      </div>
    </BottomSheet>

    <!-- ── Rename Sheet ── -->
    <BottomSheet
      :visible="renameVisible"
      :title="actionTarget?.type === 'paper' ? '重命名论文' : '重命名文件夹'"
      @close="renameVisible = false"
    >
      <div class="px-5 pb-5 pt-2 flex flex-col gap-4">
        <input
          v-if="actionTarget?.type === 'folder'"
          v-model="renameName"
          type="text"
          placeholder="新名称"
          class="input-field"
          maxlength="40"
          @keyup.enter="confirmRename"
        />
        <input
          v-else
          v-model="paperRenameName"
          type="text"
          placeholder="论文标题"
          class="input-field"
          maxlength="200"
          @keyup.enter="confirmRename"
        />
        <button
          type="button"
          class="btn-primary"
          :disabled="actionTarget?.type === 'folder' ? !renameName.trim() : !paperRenameName.trim()"
          @click="confirmRename"
        >
          确认
        </button>
      </div>
    </BottomSheet>

    <!-- ── Move Paper Sheet ── -->
    <BottomSheet
      :visible="moveSheetVisible"
      title="移动到文件夹"
      @close="moveSheetVisible = false"
    >
      <div class="pb-4">
        <button
          type="button"
          class="w-full flex items-center gap-3 px-5 py-3.5 text-[14px] text-text-secondary active:bg-bg-hover"
          @click="movePaperToFolder(null)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19" /><polyline points="19 12 12 19 5 12" /></svg>
          未分类（根目录）
        </button>
        <div class="h-px bg-border mx-4 mb-1" />
        <button
          v-for="folder in allFolders"
          :key="folder.id"
          type="button"
          class="w-full flex items-center gap-3 px-5 py-3.5 text-[14px] text-text-primary active:bg-bg-hover"
          @click="movePaperToFolder(folder.id)"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#f5b731">
            <path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z" />
          </svg>
          {{ folder.name }}
        </button>
      </div>
    </BottomSheet>

    <!-- ── Process Status Sheet ── -->
    <BottomSheet
      :visible="processStatusVisible"
      title="处理状态"
      @close="processStatusVisible = false"
    >
      <div class="px-5 pb-6 pt-2">
        <div v-if="loadingProcessStatus" class="flex justify-center py-6">
          <div class="w-6 h-6 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
        </div>
        <div v-else-if="processStatusPaper" class="space-y-3">
          <p class="text-[13px] font-semibold text-text-primary line-clamp-2">
            {{ processStatusPaper.paper_data?.short_title || processStatusPaper.paper_id }}
          </p>
          <div class="flex items-center gap-2">
            <span
              class="text-[11px] px-2 py-0.5 rounded-full font-medium"
              :class="{
                'bg-tinder-blue/15 text-tinder-blue': processStatusData?.process_status === 'processing' || processStatusPaper.process_status === 'processing',
                'bg-tinder-gold/15 text-tinder-gold': processStatusData?.process_status === 'pending' || processStatusPaper.process_status === 'pending',
                'bg-tinder-pink/15 text-tinder-pink': processStatusData?.process_status === 'failed' || processStatusPaper.process_status === 'failed',
                'bg-tinder-green/15 text-tinder-green': processStatusData?.process_status === 'completed',
              }"
            >
              {{ processStatusData?.process_status === 'completed' ? '已完成'
                : processStatusData?.process_status === 'processing' || processStatusPaper.process_status === 'processing' ? '处理中'
                : processStatusData?.process_status === 'pending' || processStatusPaper.process_status === 'pending' ? '等待中'
                : '失败' }}
            </span>
            <span v-if="processStatusData?.process_step" class="text-[12px] text-text-muted">
              {{ kbPaperStepLabel(processStatusData.process_step) }}
            </span>
          </div>
          <p v-if="processStatusData?.process_status === 'processing' || processStatusPaper.process_status === 'processing'" class="text-[12px] text-tinder-blue leading-relaxed">
            系统正在自动处理，通常需要 1-5 分钟，完成后即可查看。
          </p>
          <p v-else-if="processStatusData?.process_status === 'failed' || processStatusPaper.process_status === 'failed'" class="text-[12px] text-tinder-pink leading-relaxed">
            处理失败{{ processStatusData?.process_error ? `：${processStatusData.process_error}` : ''}}。请稍后重试或联系支持。
          </p>
          <p v-else-if="processStatusPaper.process_status === 'pending'" class="text-[12px] text-tinder-gold leading-relaxed">
            已加入处理队列，等待系统处理中…
          </p>
        </div>
      </div>
    </BottomSheet>

    <!-- ── Batch Move Sheet ── -->
    <BottomSheet
      :visible="batchMoveSheetVisible"
      title="批量移动"
      @close="batchMoveSheetVisible = false"
    >
      <div class="pb-4">
        <button type="button" class="w-full flex items-center gap-3 px-5 py-3.5 text-[14px] text-text-secondary active:bg-bg-hover" @click="batchMoveToFolder(null)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19" /><polyline points="19 12 12 19 5 12" /></svg>
          未分类（根目录）
        </button>
        <div class="h-px bg-border mx-4 mb-1" />
        <button v-for="folder in allFolders" :key="folder.id" type="button" class="w-full flex items-center gap-3 px-5 py-3.5 text-[14px] text-text-primary active:bg-bg-hover" @click="batchMoveToFolder(folder.id)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#f5b731"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z" /></svg>
          {{ folder.name }}
        </button>
      </div>
    </BottomSheet>

    <!-- ── Batch mode bottom bar ── -->
    <Transition name="slide-up">
      <div
        v-if="batchMode"
        class="fixed left-0 right-0 bg-bg/95 backdrop-blur-md border-t border-border px-4 pt-3 z-20"
        style="bottom: 0; padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));"
      >
        <div class="flex items-center gap-2 mb-3">
          <button type="button" class="text-[12px] text-tinder-blue active:opacity-70" @click="selectAll">
            {{ selectedPaperIds.size === allPapers.length ? '取消全选' : '全选' }}
          </button>
          <span class="flex-1 text-center text-[13px] font-semibold text-text-primary">已选 {{ selectedPaperIds.size }} 篇</span>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="flex-1 py-2.5 rounded-xl border border-tinder-blue/30 bg-tinder-blue/10 text-tinder-blue text-[13px] font-medium active:bg-tinder-blue/20 disabled:opacity-40"
            :disabled="selectedPaperIds.size === 0 || batchMoving"
            @click="batchMoveSheetVisible = true"
          >
            {{ batchMoving ? '移动中…' : '移动' }}
          </button>
          <button
            type="button"
            class="flex-1 py-2.5 rounded-xl border border-tinder-pink/30 bg-tinder-pink/10 text-tinder-pink text-[13px] font-medium active:bg-tinder-pink/20 disabled:opacity-40"
            :disabled="selectedPaperIds.size === 0 || batchDeleting"
            @click="batchDeleteSelected"
          >
            {{ batchDeleting ? '删除中…' : '删除' }}
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>