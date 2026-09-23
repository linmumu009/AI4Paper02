<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { API_ORIGIN, fetchUserPaperFiles, fetchKbPaperFiles, type KbScope } from '../api'
import ReadingTrialViewer from '../components/ReadingTrialViewer.vue'
import { parseReadingAnchor } from '../utils/readingAnchor'

const route = useRoute()
const paperId = computed(() => String(route.params.paperId || ''))
const scope = computed<KbScope>(() => ['kb', 'inspiration', 'mypapers'].includes(String(route.query.scope)) ? route.query.scope as KbScope : 'kb')
const mode = computed<'mineru' | 'zh' | 'bilingual'>(() => ['mineru', 'zh', 'bilingual'].includes(String(route.query.mode)) ? route.query.mode as 'mineru' | 'zh' | 'bilingual' : 'mineru')
const anchor = computed(() => parseReadingAnchor(route.hash))
const url = ref('')
const error = ref('')
const loading = ref(false)
let request = 0
watch([paperId, scope, mode], async () => {
  const current = ++request
  loading.value = true
  error.value = ''
  url.value = ''
  try {
    const files = scope.value === 'mypapers' ? await fetchUserPaperFiles(paperId.value) : await fetchKbPaperFiles(paperId.value, scope.value)
    if (current !== request) return
    const path = mode.value === 'zh' ? files.zh_static_url : mode.value === 'bilingual' ? files.bilingual_static_url : files.mineru_static_url
    if (!path) throw new Error('该版本的原文已被删除或尚未生成。')
    url.value = path.startsWith('/') ? `${API_ORIGIN}${path}` : path
  } catch (cause: any) {
    if (current === request) error.value = cause?.response?.data?.detail || cause?.message || '无法打开原文，请确认登录账号和论文权限。'
  } finally { if (current === request) loading.value = false }
}, { immediate: true })
</script>

<template>
  <main class="source-page">
    <header><strong>笔记原文定位</strong><a href="/">返回论文首页</a></header>
    <p v-if="loading" role="status">正在打开论文原文…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <template v-else-if="url">
      <p v-if="!anchor" role="status">定位信息无效，已打开原文。</p>
      <ReadingTrialViewer :key="url" :url="url" :mode="mode" :paper-id="paperId" :scope="scope" :source-anchor="anchor" />
    </template>
  </main>
</template>

<style scoped>
.source-page { height: calc(100dvh - 64px); min-height: 300px; display: flex; flex-direction: column; max-width: 1100px; margin: 0 auto; padding: 12px; }
header { display: flex; justify-content: space-between; padding: 8px 4px 14px; font-size: 14px; }
header a { text-decoration: underline; }
</style>
