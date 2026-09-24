<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { createNote, fetchNotes, type KbScope } from '../api'
import { http } from '@shared/api/client'
import { toApiKbScope } from '../api/knowledgeBase'
import type { KbNote } from '../types/paper'
import type { ReadingExcerptRequest } from '@shared/types/kb'
import { excerptHtml, type ReadingAnchor } from '../utils/readingAnchor'

const props = defineProps<{ paperId: string; scope: KbScope; mode: string; anchor: ReadingAnchor; quote: string; x: number; y: number; preferredNoteId?: number; appendToNote?: (id: number, update: () => Promise<KbNote>) => Promise<KbNote> }>()
const emit = defineEmits<{ close: []; saved: [note: KbNote] }>()
const menu = ref<HTMLElement | null>(null)
function dismissOutside(event: PointerEvent) {
  if (event.target instanceof Node && !menu.value?.contains(event.target)) emit('close')
}
function dismissOnEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close') }
}
onMounted(() => {
  document.addEventListener('pointerdown', dismissOutside, true)
  document.addEventListener('keydown', dismissOnEscape, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', dismissOutside, true)
  document.removeEventListener('keydown', dismissOnEscape, true)
})
const notes = ref<KbNote[]>([])
const chosen = ref('new')
const loading = ref(true)
const loaded = ref(false)
const saving = ref(false)
const error = ref('')
const saved = ref<KbNote | null>(null)
const newTitle = ref('阅读摘录')
// Keep one URL across retries so the append endpoint can reject duplicates.
const path = `/reading-source/${encodeURIComponent(props.paperId)}?scope=${encodeURIComponent(props.scope)}&mode=${encodeURIComponent(props.mode)}&clip=${crypto.randomUUID()}#${encodeURIComponent(JSON.stringify(props.anchor))}`
async function loadNotes() {
  loading.value = true
  error.value = ''
  try {
    notes.value = (await fetchNotes(props.paperId, props.scope)).notes.filter(note => note.type === 'markdown')
    chosen.value = String(notes.value.find(note => note.id === props.preferredNoteId)?.id ?? notes.value[0]?.id ?? 'new')
    loaded.value = true
  } catch { error.value = '无法读取当前论文的笔记，请关闭后重试。' }
  finally { loading.value = false }
}
onMounted(loadNotes)
async function save() {
  if (saving.value || saved.value) return
  saving.value = true
  error.value = ''
  try {
    if (chosen.value === 'new') saved.value = await createNote(props.paperId, newTitle.value.trim() || '阅读摘录', excerptHtml(props.quote, path), props.scope)
    else {
      const payload: ReadingExcerptRequest = { paper_id: props.paperId, scope: toApiKbScope(props.scope), text: props.quote, source_path: path }
      const update = async () => (await http.post<KbNote>(`/kb/notes/${chosen.value}/excerpt`, payload)).data
      saved.value = props.appendToNote ? await props.appendToNote(Number(chosen.value), update) : await update()
    }
    window.dispatchEvent(new CustomEvent('reading-note-saved'))
    emit('saved', saved.value)
  } catch (cause: any) { error.value = cause?.response?.data?.detail || cause?.message || '保存失败，请重试。已选文字会保留。' }
  finally { saving.value = false }
}
</script>

<template>
  <aside ref="menu" class="excerpt-menu" :style="{ left: `${x}px`, top: `${y}px` }" role="dialog" aria-label="添加摘录到笔记" @pointerup.stop @keydown.esc.stop="emit('close')">
    <div class="excerpt-top"><strong>添加到笔记</strong><button aria-label="关闭摘录菜单" @click="emit('close')">×</button></div>
    <p v-if="loading">正在读取当前论文的笔记…</p>
    <template v-else-if="saved">
      <p role="status">已添加到「{{ saved.title }}」</p>
      <p class="excerpt-hint">可以继续阅读。</p>
    </template>
    <button v-else-if="!loaded" @click="loadNotes">重新读取笔记</button>
    <template v-else>
      <label>保存到 <select v-model="chosen" aria-label="选择笔记"><option v-for="note in notes" :key="note.id" :value="String(note.id)">{{ note.title }}</option><option value="new">新建笔记</option></select></label>
      <input v-if="chosen === 'new'" v-model="newTitle" aria-label="新笔记名称" maxlength="256" />
      <button :disabled="saving" class="excerpt-save" @click="save">{{ saving ? '保存中…' : chosen === 'new' ? '新建并添加摘录' : '添加摘录' }}</button>
    </template>
    <p v-if="error" role="alert">{{ error }}</p>
  </aside>
</template>

<style scoped>
.excerpt-menu { position: fixed; z-index: 100; width: min(300px, calc(100vw - 24px)); max-height: min(360px, calc(100dvh - 24px)); overflow: auto; padding: 14px; border: 1px solid var(--trial-line); border-radius: 10px; background: var(--trial-bg); color: var(--trial-ink); box-shadow: 0 6px 28px #0003; font-size: 14px; text-indent: 0; }
.excerpt-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.excerpt-menu select, .excerpt-menu input { display: block; width: 100%; margin: 8px 0; padding: 6px; border: 1px solid var(--trial-line); background: var(--trial-bg); color: inherit; border-radius: 5px; }
.excerpt-menu button { cursor: pointer; background: transparent; color: inherit; border: 1px solid var(--trial-line); border-radius: 5px; padding: 5px 10px; }
.excerpt-menu .excerpt-save { width: 100%; margin-top: 6px; }
.excerpt-menu a { text-decoration: underline; color: inherit; }
.excerpt-hint { font-size: 12px; margin-top: 8px; }
</style>
