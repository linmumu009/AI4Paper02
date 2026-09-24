<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import NoteEditor from '../views/NoteEditor.vue'
import { fetchNotes, createNote, type KbScope } from '../api'
import type { KbNote } from '../types/paper'

const props = defineProps<{ paperId: string; scope: KbScope; preferredId?: number; latestNote?: KbNote | null }>()
const emit = defineEmits<{ close: []; sourceLink: [href: string]; selected: [id: number] }>()
const notes = ref<KbNote[]>([])
const currentId = ref<number | null>(null)
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const editor = ref<{ flushSave: () => Promise<boolean>; applyExternalUpdate: (update: () => Promise<KbNote>) => Promise<KbNote> } | null>(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    notes.value = (await fetchNotes(props.paperId, props.scope)).notes.filter(note => note.type === 'markdown')
    currentId.value = notes.value.find(note => note.id === props.preferredId)?.id ?? notes.value[0]?.id ?? null
  } catch { error.value = '笔记读取失败，请重试。' }
  finally { loading.value = false }
}
onMounted(load)
watch(() => props.latestNote, note => {
  if (!note) return
  const index = notes.value.findIndex(item => item.id === note.id)
  if (index < 0) notes.value.push(note)
  else notes.value[index] = note
  if (!currentId.value) currentId.value = note.id
})
async function flush() {
  if (busy.value) return false
  const ok = await editor.value?.flushSave() ?? true
  if (!ok) error.value = '笔记未保存，内容已保留。请点击保存后再关闭。'
  return ok
}
async function close() { if (await flush()) emit('close') }
async function select(event: Event) {
  const select = event.target as HTMLSelectElement
  const next = Number(select.value)
  select.value = String(currentId.value ?? '')
  if (!await flush()) return
  currentId.value = next
  emit('selected', next)
}
async function create() {
  if (!await flush()) return
  busy.value = true
  try {
    const note = await createNote(props.paperId, '阅读笔记', '', props.scope)
    if (!notes.value.some(item => item.id === note.id)) notes.value.push(note)
    currentId.value = note.id
    emit('selected', note.id)
    window.dispatchEvent(new CustomEvent('reading-note-saved'))
  } catch { error.value = '新建笔记失败，请重试。' }
  finally { busy.value = false }
}
async function append(id: number, update: () => Promise<KbNote>) {
  if (busy.value || loading.value || (currentId.value === id && !editor.value)) throw new Error('笔记正在准备，请稍后重试。')
  busy.value = true
  try { return currentId.value === id && editor.value ? await editor.value.applyExternalUpdate(update) : await update() }
  finally { busy.value = false }
}
function sourceClick(event: MouseEvent) {
  const link = (event.target as Element)?.closest('a[href]') as HTMLAnchorElement | null
  if (!link) return
  const url = new URL(link.href, window.location.origin)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/reading-source/')) return
  event.preventDefault()
  event.stopImmediatePropagation()
  emit('sourceLink', link.href)
}
function saved(note: { id: number; title: string }) {
  const item = notes.value.find(item => item.id === note.id)
  if (item) item.title = note.title
  window.dispatchEvent(new CustomEvent('reading-note-saved'))
}
defineExpose({ flush, append })
</script>

<template>
  <aside class="reading-notes-panel" aria-label="当前论文笔记" @keydown.esc.stop.prevent="close" @click.capture="sourceClick">
    <header><div><strong>论文笔记</strong><small>边读边记 · 自动保存</small></div><button :disabled="busy" type="button" aria-label="收起笔记" @click="close">收起</button></header>
    <div class="note-choices">
      <select v-if="notes.length" :value="currentId" aria-label="侧栏笔记" :disabled="busy" @change="select"><option v-for="note in notes" :key="note.id" :value="note.id">{{ note.title }}</option></select>
      <button type="button" :disabled="busy || loading" @click="create">＋ 新建</button>
    </div>
    <p v-if="loading" role="status" class="panel-message">正在读取笔记…</p>
    <p v-if="error" role="alert" class="panel-message">{{ error }} <button v-if="!currentId" @click="load">重试</button></p>
    <div v-if="currentId" class="note-editor-slot">
      <NoteEditor :id="String(currentId)" :key="currentId" ref="editor" embedded compact @saved="saved" />
    </div>
    <p v-else-if="!loading && !error" class="panel-message">选中原文可保存摘录，也可以新建笔记写下想法。</p>
  </aside>
</template>

<style scoped>
.reading-notes-panel { display: flex; flex-direction: column; min-height: 0; width: 380px; flex-shrink: 0; border: 1px solid var(--color-border); border-radius: 12px; overflow: hidden; background: var(--color-bg-card); color: var(--color-text-primary); }
header { display: flex; justify-content: space-between; align-items: center; padding: 14px; gap: 12px; border-bottom: 1px solid var(--color-border); }
header strong { font-size: 15px; } header small { display: block; margin-top: 3px; font-size: 11px; color: var(--color-text-muted); }
button, select { font: inherit; font-size: 12px; border: 1px solid var(--color-border); border-radius: 8px; min-height: 30px; padding: 5px 8px; background: var(--color-bg-card); color: inherit; }
button { cursor: pointer; } button:hover:not(:disabled) { background: var(--color-bg-hover); } button:focus-visible, select:focus-visible { outline: 2px solid var(--color-accent-primary); outline-offset: 2px; } button:disabled { opacity: 0.5; cursor: wait; }
.note-choices { padding: 10px 12px; display: flex; gap: 8px; } .note-choices select { min-width: 0; flex: 1; }
.note-editor-slot { flex: 1; min-height: 0; overflow: hidden; }
.panel-message { padding: 12px; font-size: 13px; }
@media (max-width: 1100px) { .reading-notes-panel { position: absolute; z-index: 40; inset: 0 0 0 auto; width: min(420px, 92vw); box-shadow: -8px 0 32px #0002; } }
</style>
