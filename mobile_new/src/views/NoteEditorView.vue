<script setup lang="ts">
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import { fetchNoteDetail, updateNote, deleteNote as deleteNoteApi, downloadNote } from '@shared/api'
import type { KbNote } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

const props = defineProps<{ id: string }>()
const router = useRouter()

const note = ref<KbNote | null>(null)
const loading = ref(true)
const saving = ref(false)
const title = ref('')
const lastSavedAt = ref('')
const dirty = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const editor = useEditor({
  extensions: [
    StarterKit,
    Image.configure({ inline: false }),
    Link.configure({ openOnClick: false }),
    Placeholder.configure({ placeholder: '开始写笔记…' }),
  ],
  content: '',
  editorProps: {
    attributes: { class: 'tiptap-mobile-editor' },
  },
  onUpdate() {
    dirty.value = true
    scheduleSave()
  },
})

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(autoSave, 3000)
}

async function autoSave() {
  if (!note.value || !editor.value || !dirty.value) return
  await doSave()
}

async function doSave() {
  if (!note.value || !editor.value || saving.value) return
  saving.value = true
  try {
    const content = editor.value.getHTML()
    await updateNote(note.value.id, { title: title.value || '未命名笔记', content })
    lastSavedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    dirty.value = false
  } catch (e) {
    showToast('保存失败')
    throw e
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const result = await fetchNoteDetail(Number(props.id))
    note.value = result
    title.value = result.title || ''
    editor.value?.commands.setContent(result.content || '')
  } catch (e: any) {
    showToast('加载笔记失败')
    router.back()
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
  editor.value?.destroy()
})

onBeforeRouteLeave(async (_to, _from, next) => {
  if (dirty.value && note.value) {
    try {
      await doSave()
      next()
    } catch {
      try {
        await showDialog({
          title: '保存失败',
          message: '笔记保存失败，确定离开并放弃修改？',
          confirmButtonText: '放弃',
          cancelButtonText: '留下',
          confirmButtonColor: 'var(--color-tinder-pink)',
        })
        next()
      } catch {
        next(false)
      }
    }
  } else {
    next()
  }
})

async function doDelete() {
  try {
    await showDialog({
      title: '删除笔记',
      message: '确定删除此笔记？此操作不可撤销。',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    if (note.value) await deleteNoteApi(note.value.id)
    showToast('已删除')
    dirty.value = false
    router.back()
  } catch {/* user cancelled */}
}

function doExport() {
  if (!note.value) return
  downloadNote(note.value.id)
  showToast('已开始下载')
}

// Toolbar actions
function toggleBold() { editor.value?.chain().focus().toggleBold().run() }
function toggleItalic() { editor.value?.chain().focus().toggleItalic().run() }
function toggleBulletList() { editor.value?.chain().focus().toggleBulletList().run() }
function toggleOrderedList() { editor.value?.chain().focus().toggleOrderedList().run() }
function toggleCode() { editor.value?.chain().focus().toggleCode().run() }
function insertHR() { editor.value?.chain().focus().setHorizontalRule().run() }
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader @back="router.back()">
      <template #title>
        <input
          v-model="title"
          type="text"
          placeholder="笔记标题"
          class="w-full bg-transparent text-[15px] font-semibold text-text-primary text-center outline-none placeholder:text-text-muted truncate"
          maxlength="80"
        />
      </template>
      <template #right>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="w-10 h-10 flex items-center justify-center text-text-secondary active:text-tinder-blue"
            aria-label="导出笔记"
            @click="doExport"
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
          <button
            type="button"
            class="w-10 h-10 flex items-center justify-center text-text-secondary active:text-tinder-pink"
            :class="{ 'text-tinder-green': !dirty && lastSavedAt }"
            :disabled="saving"
            aria-label="保存"
            @click="doSave"
          >
            <svg v-if="saving" class="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
              <polyline points="17 21 17 13 7 13 7 21" />
              <polyline points="7 3 7 8 15 8" />
            </svg>
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- Save status -->
    <div class="px-4 pb-1 shrink-0 flex items-center gap-2 -mt-1">
      <span v-if="saving" class="text-[11px] text-text-muted">保存中…</span>
      <span v-else-if="dirty" class="text-[11px] text-tinder-gold">未保存</span>
      <span v-else-if="lastSavedAt" class="text-[11px] text-text-muted">已保存 {{ lastSavedAt }}</span>
    </div>

    <!-- Loading -->
    <LoadingState v-if="loading" class="flex-1" message="加载笔记…" />

    <template v-else>
      <!-- Editor area -->
      <div class="flex-1 overflow-y-auto px-4 pb-28">
        <EditorContent :editor="editor" class="min-h-full" />
      </div>

      <!-- Formatting toolbar (fixed above virtual keyboard) -->
      <div
        class="shrink-0 border-t border-border bg-bg-card flex items-center gap-1 px-2"
        style="padding-bottom: max(8px, env(safe-area-inset-bottom, 8px)); padding-top: 6px;"
      >
        <button
          type="button"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': editor?.isActive('bold') }"
          @click="toggleBold"
        >
          <strong>B</strong>
        </button>
        <button
          type="button"
          class="toolbar-btn italic"
          :class="{ 'toolbar-btn--active': editor?.isActive('italic') }"
          @click="toggleItalic"
        >
          I
        </button>
        <div class="w-px h-5 bg-border mx-1 shrink-0" />
        <button
          type="button"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': editor?.isActive('bulletList') }"
          @click="toggleBulletList"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="9" y1="6" x2="20" y2="6" /><line x1="9" y1="12" x2="20" y2="12" /><line x1="9" y1="18" x2="20" y2="18" />
            <circle cx="4" cy="6" r="1.5" fill="currentColor" stroke="none" />
            <circle cx="4" cy="12" r="1.5" fill="currentColor" stroke="none" />
            <circle cx="4" cy="18" r="1.5" fill="currentColor" stroke="none" />
          </svg>
        </button>
        <button
          type="button"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': editor?.isActive('orderedList') }"
          @click="toggleOrderedList"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="10" y1="6" x2="21" y2="6" /><line x1="10" y1="12" x2="21" y2="12" /><line x1="10" y1="18" x2="21" y2="18" />
            <text x="2" y="8" font-size="7" fill="currentColor" stroke="none">1</text>
            <text x="2" y="14" font-size="7" fill="currentColor" stroke="none">2</text>
            <text x="2" y="20" font-size="7" fill="currentColor" stroke="none">3</text>
          </svg>
        </button>
        <button
          type="button"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': editor?.isActive('code') }"
          @click="toggleCode"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" />
          </svg>
        </button>
        <button type="button" class="toolbar-btn" @click="insertHR">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
        <div class="flex-1" />
        <button
          type="button"
          class="toolbar-btn text-tinder-pink"
          aria-label="删除笔记"
          @click="doDelete"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      </div>
    </template>
  </div>
</template>

<style>
/* Tiptap editor mobile styles */
.tiptap-mobile-editor {
  min-height: 200px;
  padding: 8px 0 80px;
  outline: none;
  color: var(--color-text-primary);
  font-size: 15px;
  line-height: 1.7;
}
.tiptap-mobile-editor p { margin: 0 0 10px; color: var(--color-text-secondary); }
.tiptap-mobile-editor h1 { font-size: 20px; font-weight: 700; margin: 20px 0 8px; color: var(--color-text-primary); }
.tiptap-mobile-editor h2 { font-size: 17px; font-weight: 600; margin: 16px 0 6px; color: var(--color-text-primary); }
.tiptap-mobile-editor h3 { font-size: 15px; font-weight: 600; margin: 12px 0 4px; color: var(--color-tinder-blue); }
.tiptap-mobile-editor ul { padding-left: 20px; margin: 0 0 10px; }
.tiptap-mobile-editor ol { padding-left: 20px; margin: 0 0 10px; }
.tiptap-mobile-editor li { margin-bottom: 4px; color: var(--color-text-secondary); }
.tiptap-mobile-editor code { background: var(--color-bg-elevated); border-radius: 4px; padding: 1px 5px; font-size: 13px; color: var(--color-tinder-blue); font-family: 'Fira Code', monospace; }
.tiptap-mobile-editor pre { background: var(--color-bg-elevated); border: 1px solid var(--color-border); border-radius: 10px; padding: 14px; overflow-x: auto; margin: 10px 0; }
.tiptap-mobile-editor pre code { background: none; padding: 0; font-size: 12px; color: var(--color-text-secondary); }
.tiptap-mobile-editor hr { border: none; border-top: 1px solid var(--color-border); margin: 16px 0; }
.tiptap-mobile-editor a { color: var(--color-tinder-blue); text-decoration: underline; }
.tiptap-mobile-editor p.is-editor-empty:first-child::before { content: attr(data-placeholder); color: var(--color-text-muted); pointer-events: none; float: left; height: 0; }

/* Toolbar buttons */
.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  cursor: pointer;
  padding: 0 6px;
  transition: background 0.1s ease;
  -webkit-tap-highlight-color: transparent;
}
.toolbar-btn:active { background: var(--color-bg-hover); }
.toolbar-btn--active { background: var(--color-bg-elevated); color: var(--color-tinder-pink); }
</style>
