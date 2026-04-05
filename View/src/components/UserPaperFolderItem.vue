<script setup lang="ts">
import type { UserPaperFolder, UserPaper, UserPaperFileViewMode, KbNote } from '../types/paper'
import type { UserPaperDerivativeType } from '../api'
import TranslateProgressRing from './TranslateProgressRing.vue'

const props = defineProps<{
  folder: UserPaperFolder
  depth: number
  expandedFolders: Set<number>
  activeFolderId: number | null
  renamingFolderId: number | null
  renamingFolderName: string
  showNewFolderInput: boolean
  newFolderParentId: number | null
  newFolderName: string
  checkedPapers: Set<string>
  batchMode: boolean
  expandedPaperLinks: Set<string>
  activeUserPaperId?: string | null
  activeViewMdKey?: string | null
  /** Notes for my papers: map of paper_id → notes array */
  paperNotes?: Map<string, KbNote[]>
  /** Paper ID whose "+" add menu is currently open */
  addMenuPaperId?: string | null
}>()

const emit = defineEmits<{
  'toggle-folder': [id: number]
  'select-folder': [id: number]
  'open-folder-menu': [e: MouseEvent, folder: UserPaperFolder]
  'open-paper-menu': [e: MouseEvent, paper: UserPaper]
  'open-paper': [paperId: string]
  'toggle-check': [paperId: string]
  'toggle-paper-links': [paperId: string]
  'view-user-paper-md': [paper: UserPaper, mode: UserPaperFileViewMode]
  'open-paper-derivative-menu': [e: MouseEvent, paper: UserPaper, derivative: UserPaperDerivativeType]
  'translate-paper': [paper: UserPaper]
  'update:renamingFolderName': [name: string]
  'confirm-rename': []
  'cancel-rename': []
  'update:newFolderName': [name: string]
  'confirm-new-folder': []
  'cancel-new-folder': []
  /** My papers "+" button actions */
  'toggle-add-menu': [paperId: string]
  'create-note': [paperId: string]
  'upload-file': [paperId: string]
  'add-link': [paperId: string]
  'open-note': [note: KbNote]
  'open-note-menu': [e: MouseEvent, note: KbNote]
}>()

function processStatusIcon(status: string): string {
  if (status === 'completed') return '✅'
  if (status === 'failed') return '❌'
  if (status === 'processing' || status === 'pending') return '⏳'
  return '○'
}

function processStatusColor(status: string): string {
  if (status === 'completed') return 'text-green-500'
  if (status === 'failed') return 'text-red-500'
  if (status === 'processing' || status === 'pending') return 'text-amber-500'
  return 'text-text-muted'
}

function subLinkPadding(): Record<string, string> {
  const pl = 36 + (props.depth + 2) * 14
  return { paddingLeft: `${pl}px`, paddingRight: '8px' }
}

function mdSubKey(paperId: string, mode: UserPaperFileViewMode): string {
  return `${paperId}:${mode}`
}

function subLinkRowClass(paperId: string, mode: UserPaperFileViewMode): string {
  const active = props.activeViewMdKey === mdSubKey(paperId, mode)
  const base =
    'flex items-center gap-2 py-1.5 px-2 rounded transition-colors group/note cursor-pointer'
  if (active) {
    return `${base} bg-amber-500/8 text-amber-600 dark:text-amber-400`
  }
  return `${base} hover:bg-bg-hover`
}

function noteIcon(type: string): string {
  if (type === 'file') return '📎'
  if (type === 'link') return '🔗'
  return '📝'
}
</script>

<template>
  <div>
    <!-- Folder row -->
    <div
      class="flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer select-none group transition-colors"
      :class="activeFolderId === folder.id
        ? 'bg-tinder-blue/10 text-tinder-blue'
        : 'hover:bg-bg-hover text-text-secondary'"
      :style="{ paddingLeft: `${8 + depth * 16}px` }"
      @click.stop="emit('toggle-folder', folder.id); emit('select-folder', folder.id)"
    >
      <!-- Expand arrow -->
      <svg
        class="w-3 h-3 shrink-0 transition-transform duration-150"
        :class="expandedFolders.has(folder.id) ? 'rotate-90' : ''"
        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <polyline points="9 18 15 12 9 6"/>
      </svg>

      <!-- Folder icon -->
      <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>

      <!-- Rename input -->
      <input
        v-if="renamingFolderId === folder.id"
        class="flex-1 bg-bg-elevated border border-tinder-blue/50 rounded px-1.5 py-0.5 text-xs text-text-primary focus:outline-none"
        :value="renamingFolderName"
        autofocus
        @input="emit('update:renamingFolderName', ($event.target as HTMLInputElement).value)"
        @keydown.enter.stop="emit('confirm-rename')"
        @keydown.escape.stop="emit('cancel-rename')"
        @blur="emit('confirm-rename')"
        @click.stop
      />
      <!-- Folder name + count -->
      <template v-else>
        <span class="flex-1 min-w-0 text-xs font-medium truncate">{{ folder.name }}</span>
        <span class="text-[10px] text-text-muted shrink-0">{{ folder.papers?.length ?? 0 }}</span>
        <!-- Menu button -->
        <button
          class="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
          @click.stop="emit('open-folder-menu', $event, folder)"
        >⋯</button>
      </template>
    </div>

    <!-- Folder contents (expanded) -->
    <template v-if="expandedFolders.has(folder.id)">
      <!-- New subfolder input -->
      <div
        v-if="showNewFolderInput && newFolderParentId === folder.id"
        class="flex items-center gap-2 px-2 py-2"
        :style="{ paddingLeft: `${8 + (depth + 1) * 16}px` }"
      >
        <svg class="w-4 h-4 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <input
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-tinder-blue/50"
          :value="newFolderName"
          placeholder="文件夹名称..."
          autofocus
          @input="emit('update:newFolderName', ($event.target as HTMLInputElement).value)"
          @keydown.enter.stop="emit('confirm-new-folder')"
          @keydown.escape.stop="emit('cancel-new-folder')"
          @blur="emit('confirm-new-folder')"
          @click.stop
        />
      </div>

      <!-- Subfolders (recursive) -->
      <UserPaperFolderItem
        v-for="child in folder.children"
        :key="child.id"
        :folder="child"
        :depth="depth + 1"
        :expanded-folders="expandedFolders"
        :active-folder-id="activeFolderId"
        :active-user-paper-id="activeUserPaperId"
        :active-view-md-key="activeViewMdKey"
        :renaming-folder-id="renamingFolderId"
        :renaming-folder-name="renamingFolderName"
        :show-new-folder-input="showNewFolderInput"
        :new-folder-parent-id="newFolderParentId"
        :new-folder-name="newFolderName"
        :checked-papers="checkedPapers"
        :batch-mode="batchMode"
        :expanded-paper-links="expandedPaperLinks"
        :paper-notes="paperNotes"
        :add-menu-paper-id="addMenuPaperId"
        @toggle-folder="(id) => emit('toggle-folder', id)"
        @select-folder="(id) => emit('select-folder', id)"
        @open-folder-menu="(e, f) => emit('open-folder-menu', e, f)"
        @open-paper-menu="(e, p) => emit('open-paper-menu', e, p)"
        @open-paper="(id) => emit('open-paper', id)"
        @toggle-check="(id) => emit('toggle-check', id)"
        @toggle-paper-links="(id) => emit('toggle-paper-links', id)"
        @view-user-paper-md="(p, m) => emit('view-user-paper-md', p, m)"
        @open-paper-derivative-menu="(e, p, d) => emit('open-paper-derivative-menu', e, p, d)"
        @translate-paper="(p) => emit('translate-paper', p)"
        @update:renamingFolderName="(v) => emit('update:renamingFolderName', v)"
        @confirm-rename="emit('confirm-rename')"
        @cancel-rename="emit('cancel-rename')"
        @update:newFolderName="(v) => emit('update:newFolderName', v)"
        @confirm-new-folder="emit('confirm-new-folder')"
        @cancel-new-folder="emit('cancel-new-folder')"
        @toggle-add-menu="(id) => emit('toggle-add-menu', id)"
        @create-note="(id) => emit('create-note', id)"
        @upload-file="(id) => emit('upload-file', id)"
        @add-link="(id) => emit('add-link', id)"
        @open-note="(note) => emit('open-note', note)"
        @open-note-menu="(e, note) => emit('open-note-menu', e, note)"
      />

      <!-- Papers in this folder -->
      <div
        v-for="paper in folder.papers"
        :key="paper.paper_id"
        class="flex flex-col rounded-lg group transition-colors"
        :class="[
          batchMode ? '' : 'hover:bg-bg-hover',
          !batchMode && activeUserPaperId === paper.paper_id ? 'bg-amber-500/8' : '',
        ]"
        :style="{ marginLeft: `${(depth + 1) * 16}px` }"
      >
        <div
          class="flex items-center gap-2 px-2 py-1.5 cursor-pointer"
          @click.stop="batchMode ? emit('toggle-check', paper.paper_id) : emit('open-paper', paper.paper_id)"
        >
          <!-- Checkbox (batch mode) -->
          <input
            v-if="batchMode"
            type="checkbox"
            :checked="checkedPapers.has(paper.paper_id)"
            class="w-3.5 h-3.5 shrink-0 cursor-pointer rounded accent-tinder-pink"
            @click.stop
            @change="emit('toggle-check', paper.paper_id)"
          />
          <button
            v-else-if="!batchMode && paper.process_status === 'completed'"
            type="button"
            class="shrink-0 w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded p-0"
            title="展开文件链接"
            @click.stop="emit('toggle-paper-links', paper.paper_id)"
          >
            <svg
              class="w-3 h-3 transition-transform"
              :class="expandedPaperLinks.has(paper.paper_id) ? 'rotate-90' : ''"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
          <div v-else class="shrink-0 w-5" />
          <!-- Status icon -->
          <span
            v-if="!batchMode && (paper.process_status === 'processing' || paper.process_status === 'pending')"
            class="inline-block w-4 text-center text-amber-500 animate-spin text-xs leading-none shrink-0"
          >⟳</span>
          <span
            v-else-if="!batchMode"
            :class="processStatusColor(paper.process_status)"
            class="inline-block w-4 text-center text-xs leading-none shrink-0"
          >{{ processStatusIcon(paper.process_status) }}</span>

          <!-- Title -->
          <span class="flex-1 min-w-0 text-xs text-text-primary truncate leading-tight">
            {{ paper.title || '（未命名）' }}
          </span>

          <!-- + Add button -->
          <div v-if="!batchMode" class="relative shrink-0">
            <button
              class="w-6 h-6 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
              title="添加笔记/文件"
              @click.stop="emit('toggle-add-menu', paper.paper_id)"
            >+</button>
            <div
              v-if="addMenuPaperId === paper.paper_id"
              class="absolute right-0 top-6 z-50 w-36 bg-bg-elevated border border-border rounded-lg shadow-lg py-1 text-xs"
              @click.stop
            >
              <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="emit('create-note', paper.paper_id)"><span>📝</span> 新建笔记</button>
              <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="emit('upload-file', paper.paper_id)"><span>📎</span> 上传文件</button>
              <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="emit('add-link', paper.paper_id)"><span>🔗</span> 添加链接</button>
            </div>
          </div>

          <!-- Menu -->
          <button
            class="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            @click.stop="emit('open-paper-menu', $event, paper)"
          >⋯</button>
        </div>

        <div
          v-if="!batchMode && paper.process_status === 'completed' && expandedPaperLinks.has(paper.paper_id)"
          class="pb-1"
          @click.stop
        >
          <div
            v-if="paper.pdf_static_url"
            :class="subLinkRowClass(paper.paper_id, 'pdf')"
            :style="subLinkPadding()"
            @click="emit('view-user-paper-md', paper, 'pdf')"
          >
            <span class="text-xs shrink-0">📄</span>
            <span class="text-xs text-text-secondary truncate flex-1">原 PDF</span>
          </div>
          <div
            v-if="paper.mineru_static_url"
            :class="[subLinkRowClass(paper.paper_id, 'mineru'), 'group !gap-1']"
            :style="subLinkPadding()"
          >
            <div
              class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
              @click="emit('view-user-paper-md', paper, 'mineru')"
            >
              <span class="text-xs shrink-0">📋</span>
              <span class="text-xs text-text-secondary truncate flex-1">MinerU 解析 (Markdown)</span>
            </div>
            <button
              type="button"
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
              title="更多"
              @click.stop="emit('open-paper-derivative-menu', $event, paper, 'mineru')"
            >⋯</button>
          </div>
          <div
            v-else
            class="flex items-center gap-2 py-1.5 px-2 rounded"
            :style="subLinkPadding()"
          >
            <span class="text-xs shrink-0 text-text-muted">📋</span>
            <span class="text-xs text-text-muted truncate flex-1">MinerU：请重新「处理」生成</span>
          </div>
          <div
            v-if="paper.zh_static_url"
            :class="[subLinkRowClass(paper.paper_id, 'zh'), 'group !gap-1']"
            :style="subLinkPadding()"
          >
            <div
              class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
              @click="emit('view-user-paper-md', paper, 'zh')"
            >
              <span class="text-xs shrink-0">🇨🇳</span>
              <span class="text-xs text-text-secondary truncate flex-1">中文翻译版</span>
            </div>
            <button
              type="button"
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
              title="更多"
              @click.stop="emit('open-paper-derivative-menu', $event, paper, 'zh')"
            >⋯</button>
          </div>
          <div
            v-if="paper.bilingual_static_url"
            :class="[subLinkRowClass(paper.paper_id, 'bilingual'), 'group !gap-1']"
            :style="subLinkPadding()"
          >
            <div
              class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
              @click="emit('view-user-paper-md', paper, 'bilingual')"
            >
              <span class="text-xs shrink-0">🔀</span>
              <span class="text-xs text-text-secondary truncate flex-1">中英文对照版</span>
            </div>
            <button
              type="button"
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
              title="更多"
              @click.stop="emit('open-paper-derivative-menu', $event, paper, 'bilingual')"
            >⋯</button>
          </div>
          <div
            v-if="paper.mineru_static_url && !paper.zh_static_url && paper.translate_status !== 'processing'"
            class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/note cursor-pointer"
            :style="subLinkPadding()"
            @click="emit('translate-paper', paper)"
          >
            <span class="text-xs shrink-0">✨</span>
            <span class="text-xs text-tinder-pink truncate flex-1 font-medium">生成中文翻译与对照</span>
          </div>
          <div
            v-if="paper.mineru_static_url && !paper.zh_static_url && paper.translate_status === 'processing'"
            class="flex items-center gap-2 py-1.5 px-2 rounded"
            :style="subLinkPadding()"
          >
            <span class="text-xs shrink-0">⏳</span>
            <span class="text-xs text-amber-500 truncate flex-1">翻译中…</span>
            <TranslateProgressRing :percent="paper.translate_progress ?? 0" />
          </div>
          <div
            v-if="paper.translate_status === 'failed' && paper.translate_error"
            class="flex items-center gap-2 py-1.5 px-2"
            :style="subLinkPadding()"
          >
            <span class="text-xs text-red-500 truncate">{{ paper.translate_error }}</span>
          </div>
          <!-- Notes section -->
          <div
            v-for="note in (paperNotes?.get(paper.paper_id) || [])"
            :key="note.id"
            class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/mpnote cursor-pointer"
            :style="subLinkPadding()"
            @click="emit('open-note', note)"
          >
            <span class="text-xs shrink-0">{{ noteIcon(note.type) }}</span>
            <span class="text-xs text-text-secondary truncate flex-1">{{ note.title }}</span>
            <button
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/mpnote:opacity-100 transition-opacity"
              @click.stop="emit('open-note-menu', $event, note)"
            >⋯</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
