<script setup lang="ts">
import { ref } from 'vue'
import type { KbCompareResultsTree, KbCompareResult, KbCompareFolder } from '../../types/paper'
import { renameCompareResult, deleteCompareResult } from '../../api'

const props = defineProps<{
  compareTree: KbCompareResultsTree | null
}>()

const emit = defineEmits<{
  openCompareResult: [resultId: number]
  refreshCompare: []
  /** Requests parent to show the shared context menu for a compare result */
  openMenu: [event: MouseEvent, result: KbCompareResult]
  startNewCompare: []
}>()

const expandedFolders = ref<Set<number>>(new Set())
const renamingId = ref<number | null>(null)
const renamingTitle = ref('')
let _renaming = false

function toggleFolder(folderId: number) {
  const next = new Set(expandedFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedFolders.value = next
}

function startRename(result: KbCompareResult) {
  renamingId.value = result.id
  renamingTitle.value = result.title
  _renaming = false
}

async function confirmRename() {
  if (_renaming) return
  _renaming = true
  const id = renamingId.value
  if (id === null) return
  const title = renamingTitle.value.trim()
  renamingId.value = null
  if (!title) return
  try {
    await renameCompareResult(id, title)
    emit('refreshCompare')
  } catch {}
}

async function handleDelete(id: number) {
  try {
    await deleteCompareResult(id)
    emit('refreshCompare')
  } catch {}
}

/** Exposed so parent can trigger rename from the shared context menu */
defineExpose({ startRename, handleDelete })
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 pt-3 pb-2 border-t border-b border-border shrink-0">
      <div class="flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
        </svg>
        <span class="text-xs font-semibold text-text-primary">对比库</span>
      </div>
      <button
        class="text-[11px] text-text-muted hover:text-accent-primary transition-colors px-2 py-1 rounded-lg hover:bg-bg-elevated cursor-pointer border-none bg-transparent"
        @click="emit('refreshCompare')"
      >刷新</button>
    </div>

    <!-- CTA button -->
    <div class="px-3 pt-2 pb-1 shrink-0">
      <button
        class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] border-none cursor-pointer hover:opacity-90 transition-opacity"
        @click="emit('startNewCompare')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
        </svg>
        发起对比分析
      </button>
    </div>

    <!-- Scrollable content -->
    <div class="flex-1 overflow-y-auto py-1">
    <template v-if="compareTree">
      <!-- Compare folders -->
      <div
        v-for="folder in compareTree.folders"
        :key="folder.id"
        class="border-b border-border/30 last:border-b-0"
      >
        <!-- Folder row -->
        <div
          class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
          @click="toggleFolder(folder.id)"
        >
          <!-- Expand chevron -->
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

          <div class="min-w-0 flex-1">
            <div class="text-xs font-semibold text-text-primary truncate">{{ folder.name }}</div>
            <div class="text-[10px] text-text-muted">{{ folder.results.length }} 项</div>
          </div>
        </div>
        <!-- In-folder results -->
        <div v-if="expandedFolders.has(folder.id)" class="pl-4">
          <div
            v-for="result in folder.results"
            :key="result.id"
            class="border-b border-border/20 last:border-b-0"
          >
            <div
              class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
              @click="emit('openCompareResult', result.id)"
            >
              <div class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] ring-1 ring-white/20 text-white text-[10px] font-bold">
                {{ result.paper_ids.length }}
              </div>
              <template v-if="renamingId === result.id">
                <input
                  v-model="renamingTitle"
                  class="flex-1 bg-bg-elevated border border-border rounded px-2 py-0.5 text-xs text-text-primary focus:outline-none focus:border-[#8b5cf6]/50 min-w-0"
                  autofocus
                  @keydown.enter="confirmRename"
                  @keydown.escape="renamingId = null"
                  @blur="confirmRename"
                  @click.stop
                />
              </template>
              <template v-else>
                <div class="min-w-0 flex-1">
                  <div class="text-xs font-medium text-text-primary truncate">{{ result.title }}</div>
                  <div class="text-[10px] text-text-muted">{{ result.paper_ids.length }} 篇</div>
                </div>
                <button
                  class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                  @click.stop="emit('openMenu', $event, result)"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5">
                    <circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>
                  </svg>
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Root compare results -->
      <div
        v-for="result in compareTree.results"
        :key="result.id"
        class="border-b border-border/30 last:border-b-0"
      >
        <div
          class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
          @click="emit('openCompareResult', result.id)"
        >
          <div class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] ring-1 ring-white/20 text-white text-[10px] font-bold">
            {{ result.paper_ids.length }}
          </div>
          <template v-if="renamingId === result.id">
            <input
              v-model="renamingTitle"
              class="flex-1 bg-bg-elevated border border-border rounded px-2 py-0.5 text-xs text-text-primary focus:outline-none focus:border-[#8b5cf6]/50 min-w-0"
              autofocus
              @keydown.enter="confirmRename"
              @keydown.escape="renamingId = null"
              @blur="confirmRename"
              @click.stop
            />
          </template>
          <template v-else>
            <div class="min-w-0 flex-1">
              <div class="text-xs font-medium text-text-primary truncate">{{ result.title }}</div>
              <div class="text-[10px] text-text-muted">{{ result.paper_ids.length }} 篇</div>
            </div>
            <button
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
              @click.stop="emit('openMenu', $event, result)"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5">
                <circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>
              </svg>
            </button>
          </template>
        </div>
      </div>

      <!-- Empty compare state -->
      <div
        v-if="compareTree.folders.length === 0 && compareTree.results.length === 0"
        class="flex flex-col items-center justify-center flex-1 py-10 px-4 text-center text-text-muted"
      >
        <div class="w-8 h-8 mb-3 rounded-full bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] opacity-25 flex items-center justify-center">
          <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
        </div>
        <p class="text-sm font-medium mb-1">暂无对比结果</p>
        <p class="text-[11px] leading-relaxed text-text-muted/70">选中 2-5 篇论文后点击「对比分析」，结果会保存在这里。</p>
      </div>
    </template>
    <div v-else class="text-center py-8">
      <p class="text-xs text-text-muted">加载中...</p>
    </div>
    </div><!-- /scrollable content -->
  </div>
</template>
