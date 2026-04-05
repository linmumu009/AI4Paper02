<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGlobalChat } from '../composables/useGlobalChat'
import { isAuthenticated } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const { isOpen, chatDrawerWidthPx, open, isDigestInPanelView, requestDigestReset } = useGlobalChat()

/** auth 页面：两个按钮都隐藏 */
const isAuthPage = computed(() =>
  route.name === 'login' || route.name === 'register',
)

/** 当前在推荐首页 */
const isDigestPage = computed(() => route.name === 'digest')

/**
 * 显示「回到推荐」的场景：
 * 1. 深层内容页（从主导航进入的具体详情页）
 * 2. 推荐首页且处于面板视图（打开了论文详情、笔记编辑等）
 */
const deepContentPages = new Set(['paper-detail', 'note-editor', 'idea-detail', 'my-papers', 'community-post', 'profile', 'advanced-settings'])
const showBackToDigest = computed(() =>
  !isAuthPage.value && (
    deepContentPages.has(route.name as string) ||
    (isDigestPage.value && isDigestInPanelView.value)
  ),
)

/** 两个按钮跟随抽屉一起左移，保证不被遮挡 */
const actionsStyle = computed(() => {
  if (!isOpen.value) return {}
  return { right: `calc(${chatDrawerWidthPx.value}px + 1rem)` }
})

function goToDigest() {
  if (isDigestPage.value) {
    // 已在推荐页：通过 shared ref 通知 DailyDigest 执行清理逻辑
    requestDigestReset()
  } else {
    router.push({ name: 'digest' })
  }
}
</script>

<template>
  <div
    v-if="!isAuthPage"
    class="fixed bottom-4 sm:bottom-8 right-4 sm:right-8 z-50 flex flex-col items-end gap-3 transition-[right] duration-200 ease-out"
    :style="actionsStyle"
  >
    <button
      v-if="showBackToDigest"
      class="px-3 py-1.5 sm:px-4 sm:py-2 rounded-full bg-brand-gradient text-xs sm:text-sm font-semibold text-white shadow-lg border-none cursor-pointer hover:opacity-90 transition-opacity"
      @click="goToDigest"
    >
      回到推荐
    </button>

    <button
      v-if="isAuthenticated"
      type="button"
      class="w-12 h-12 sm:w-14 sm:h-14 rounded-full shadow-lg border-none cursor-pointer flex items-center justify-center text-xl sm:text-2xl bg-brand-gradient-br text-white hover:opacity-90 transition-opacity"
      title="AI 助手"
      aria-label="打开 AI 助手"
      @click="open()"
    >
      💬
    </button>
  </div>
</template>
