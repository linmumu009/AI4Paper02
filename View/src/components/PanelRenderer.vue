<script setup lang="ts">
import { ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import PaperDetailBody from './PaperDetailBody.vue'
import PaperDetailEmbed from '../views/PaperDetailEmbed.vue'
import NoteEditor from '../views/NoteEditor.vue'
import MarkdownViewer from './MarkdownViewer.vue'
import ComparePanel from './ComparePanel.vue'
import CompareResultViewer from './CompareResultViewer.vue'
import IdeaDetailPanel from './idea/IdeaDetailPanel.vue'
import PaperChat from './PaperChat.vue'
import PdfPanel from './panels/PdfPanel.vue'
import { PANEL_IDS } from '../composables/usePanelLayout'
import type { ContentLayoutContext } from './ContentLayout.vue'

type NoteEditorExposed = ComponentPublicInstance & {
  isEffectivelyEmpty: () => boolean
  flushSave: () => Promise<void>
}

const props = defineProps<{
  panelId: string
  context: ContentLayoutContext
  /** root-class passed to MarkdownViewer; differs between single-panel and split-panel slots */
  markdownRootClass?: string
}>()

const emit = defineEmits<{
  noteSaved: [payload?: { id: number; title: string }]
  closeNote: []
  closeCompare: []
  closeCompareResult: []
  closeIdea: []
  ideaOpenPaper: [paperId: string]
  compareSaved: [resultId: number]
  openPdf: []
  openChat: []
}>()

const noteEditorRef = ref<NoteEditorExposed | null>(null)

function isBody(): boolean {
  return !!props.context.paperDetail
}

function bodyProps() {
  const d = props.context.paperDetail!
  return {
    detail: d,
    effectiveSource: props.context.userPaperData ? ('user_upload' as const) : undefined,
  }
}

function fetchProps() {
  return {
    id: props.context.paperId,
    userPaperData: props.context.userPaperData,
    source: props.context.userPaperData ? ('user_upload' as const) : undefined,
  }
}

const mdRootClass = props.markdownRootClass ?? 'min-h-[200px]'

defineExpose({
  getNoteEditor: (): NoteEditorExposed | null => noteEditorRef.value,
})
</script>

<template>
  <template v-if="panelId === PANEL_IDS.PAPER_DETAIL">
    <PaperDetailBody
      v-if="isBody()"
      v-bind="bodyProps()"
      @open-pdf="emit('openPdf')"
      @open-chat="emit('openChat')"
    />
    <PaperDetailEmbed
      v-else
      v-bind="fetchProps()"
      @open-pdf="emit('openPdf')"
      @open-chat="emit('openChat')"
    />
  </template>
  <PdfPanel
    v-else-if="panelId === PANEL_IDS.PDF_VIEWER"
    :src="context.pdfViewerSrc || ''"
    :title="context.pdfTitle"
    :bare-url="context.pdfUrl"
    :hide-header="context.hidePdfHeader"
  />
  <NoteEditor
    v-else-if="panelId === PANEL_IDS.NOTE_EDITOR && context.noteEditor"
    :id="String(context.noteEditor.id)"
    ref="noteEditorRef"
    embedded
    @close="emit('closeNote')"
    @saved="emit('noteSaved', $event)"
  />
  <MarkdownViewer
    v-else-if="panelId === PANEL_IDS.MARKDOWN_VIEWER && context.mdUrl"
    :url="context.mdUrl"
    :root-class="mdRootClass"
  />
  <MarkdownViewer
    v-else-if="panelId === PANEL_IDS.MARKDOWN_MINERU && context.mdMineruUrl"
    :url="context.mdMineruUrl"
    :root-class="mdRootClass"
    mode="mineru"
  />
  <MarkdownViewer
    v-else-if="panelId === PANEL_IDS.MARKDOWN_ZH && context.mdZhUrl"
    :url="context.mdZhUrl"
    :root-class="mdRootClass"
    mode="zh"
  />
  <MarkdownViewer
    v-else-if="panelId === PANEL_IDS.MARKDOWN_BILINGUAL && context.mdBilingualUrl"
    :url="context.mdBilingualUrl"
    :root-class="mdRootClass"
    mode="bilingual"
  />
  <ComparePanel
    v-else-if="panelId === PANEL_IDS.COMPARE"
    :paper-ids="context.comparingPaperIds || []"
    :compare-result-ids="context.comparingResultIds"
    :paper-titles="context.comparePaperTitles"
    :scope="context.compareScope ?? 'kb'"
    @close="emit('closeCompare')"
    @saved="emit('compareSaved', $event)"
  />
  <CompareResultViewer
    v-else-if="panelId === PANEL_IDS.COMPARE_RESULT && context.compareResultId != null"
    :result-id="context.compareResultId"
    :paper-titles="context.comparePaperTitles"
    @close="emit('closeCompareResult')"
  />
  <IdeaDetailPanel
    v-else-if="panelId === PANEL_IDS.IDEA_DETAIL && context.ideaCandidateId != null"
    :candidate-id="context.ideaCandidateId"
    @close="emit('closeIdea')"
    @open-paper="emit('ideaOpenPaper', $event)"
  />
  <PaperChat
    v-else-if="panelId === PANEL_IDS.AI_CHAT"
    :paper-id="context.paperId || context.paperDetail?.summary.paper_id"
    :paper-title="context.paperDetail?.summary.short_title || context.paperDetail?.summary['📖标题']"
    :paper-summary="context.paperDetail?.summary ?? context.paperSummary"
    @note-saved="emit('noteSaved')"
  />
</template>
