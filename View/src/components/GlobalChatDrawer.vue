<script setup lang="ts">
import { watch, onMounted, onUnmounted, computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import PaperChat from './PaperChat.vue'
import { useGlobalChat } from '../composables/useGlobalChat'
import { fetchPaperDetail } from '../api'

const route = useRoute()
const {
  isOpen,
  drawerMode,
  paperContext,
  manualPaperId,
  effectivePaperId,
  open,
  close,
  setDrawerMode,
  setPaperContext,
  clearPaperContext,
  browsingContext,
  chatDrawerWidthPx,
  setDrawerWidth,
  resetDrawerWidthToDefault,
  applyBrowsingToPaperContext,
} = useGlobalChat()

const drawerWidth = computed(() => chatDrawerWidthPx.value)
const isResizingDrawer = ref(false)

function startDrawerResize(e: MouseEvent) {
  e.preventDefault()
  isResizingDrawer.value = true
  const startClientX = e.clientX
  const startWidth = chatDrawerWidthPx.value

  function onMove(ev: MouseEvent) {
    const deltaX = ev.clientX - startClientX
    setDrawerWidth(startWidth - deltaX)
  }

  function onUp() {
    isResizingDrawer.value = false
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

async function syncRoutePaperContext() {
  if (route.name === 'paper-detail' && route.params.id) {
    const pid = String(route.params.id)
    try {
      const d = await fetchPaperDetail(pid)
      if (d?.summary) {
        setPaperContext({
          paperId: pid,
          title: d.summary.short_title || d.summary['📖标题'] || pid,
          summary: d.summary,
        })
        return
      }
    } catch {
      setPaperContext({ paperId: pid, title: pid })
      return
    }
  } else if (browsingContext.value?.paperId) {
    applyBrowsingToPaperContext()
  } else {
    clearPaperContext()
  }
}

watch(
  () => [route.name, route.params.id],
  () => {
    syncRoutePaperContext()
  },
  { immediate: true },
)

watch(
  browsingContext,
  (b) => {
    if (route.name === 'paper-detail') return
    if (b?.paperId) {
      applyBrowsingToPaperContext()
    } else {
      clearPaperContext()
    }
  },
  { deep: true },
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) close()
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

</script>

<template>
  <!-- 推挤式侧栏：无全屏遮罩，不遮挡主内容 -->
  <Teleport to="body">
    <Transition name="drawer-slide">
      <aside
        v-if="isOpen"
        class="fixed top-0 right-0 z-[80] h-full flex flex-row bg-bg border-l border-border shadow-2xl"
        :style="{ width: drawerWidth + 'px', maxWidth: '100vw' }"
      >
        <div
          class="shrink-0 w-2 flex items-center justify-center self-stretch cursor-col-resize group z-10 border-r border-border/60"
          title="拖动调整宽度，双击恢复默认"
          @mousedown="startDrawerResize"
          @dblclick.prevent="resetDrawerWidthToDefault"
        >
          <div
            class="w-[3px] h-10 rounded-full transition-all duration-200"
            :class="isResizingDrawer
              ? 'bg-tinder-pink h-full rounded-none'
              : 'bg-border group-hover:bg-tinder-pink/60 group-hover:h-full group-hover:rounded-none'"
          />
        </div>
        <div class="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
        <div class="shrink-0 flex items-center gap-2 px-3 py-2 border-b border-border">
          <span class="text-sm font-semibold text-text-primary truncate">AI 助手</span>
          <div class="ml-auto flex items-center gap-1 flex-wrap justify-end">
            <button
              type="button"
              class="text-xs px-2 py-1 rounded-lg border border-border bg-bg-elevated cursor-pointer"
              :class="drawerMode === 'general' ? 'border-tinder-blue text-tinder-blue' : ''"
              @click="setDrawerMode('general')"
            >
              通用
            </button>
            <button
              type="button"
              class="text-xs px-2 py-1 rounded-lg border border-border bg-bg-elevated cursor-pointer"
              :class="drawerMode === 'paper' ? 'border-tinder-blue text-tinder-blue' : ''"
              @click="setDrawerMode('paper')"
            >
              论文
            </button>
            <button
              type="button"
              class="text-xs px-2 py-1 rounded-lg text-text-muted hover:text-text-primary cursor-pointer border-none bg-transparent"
              @click="close"
            >
              ✕
            </button>
          </div>
        </div>

        <div
          v-if="drawerMode === 'paper'"
          class="shrink-0 px-3 py-2 border-b border-border space-y-1"
        >
          <label class="text-[10px] text-text-muted uppercase tracking-wide">论文 ID（可改）</label>
          <input
            v-model="manualPaperId"
            type="text"
            class="w-full text-xs bg-bg-elevated border border-border rounded-lg px-2 py-1.5 text-text-primary"
            placeholder="arXiv ID 或 up_…"
          />
          <p v-if="paperContext?.title" class="text-[11px] text-text-muted truncate">
            上下文：{{ paperContext.title }}
          </p>
          <button
            type="button"
            class="text-[11px] text-tinder-blue bg-transparent border-none cursor-pointer p-0"
            @click="clearPaperContext(); manualPaperId = ''"
          >
            清除关联
          </button>
        </div>

        <div class="flex-1 min-h-0 overflow-hidden">
          <PaperChat
            v-if="drawerMode === 'general'"
            chat-mode="general"
            :show-close-button="false"
          />
          <PaperChat
            v-else-if="effectivePaperId"
            :paper-id="effectivePaperId"
            :paper-title="paperContext?.title"
            :paper-summary="paperContext?.summary"
            :show-close-button="false"
          />
          <div
            v-else
            class="p-6 text-center text-sm text-text-muted"
          >
            请输入论文 ID 或打开某篇论文详情以关联上下文
          </div>
        </div>
        </div>
      </aside>
    </Transition>
  </Teleport>

</template>

<style scoped>
.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: transform 0.25s ease;
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(100%);
}
</style>
