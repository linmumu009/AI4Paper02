<script setup lang="ts">
import xMarkIcon from '../../assets/heroicons/x-mark.svg'

withDefaults(defineProps<{
  contextOpen?: boolean
  contextLabel?: string
}>(), {
  contextOpen: false,
  contextLabel: '研究上下文',
})

const emit = defineEmits<{
  closeContext: []
  documentScroll: [progress: number]
}>()

function handleDocumentScroll(event: Event) {
  const target = event.currentTarget as HTMLElement
  const scrollable = target.scrollHeight - target.clientHeight
  emit('documentScroll', scrollable > 0 ? target.scrollTop / scrollable : 0)
}
</script>

<template>
  <section class="immersive-workspace-shell">
    <nav class="immersive-workspace-shell__rail" aria-label="沉浸阅读快捷入口">
      <slot name="rail" />
    </nav>

    <main class="immersive-workspace-shell__document" @scroll.passive="handleDocumentScroll">
      <slot />
    </main>

    <button
      v-if="contextOpen"
      type="button"
      class="immersive-workspace-shell__backdrop"
      aria-label="关闭研究上下文"
      @click="emit('closeContext')"
    />

    <aside
      class="immersive-workspace-shell__context"
      :class="{ 'immersive-workspace-shell__context--open': contextOpen }"
      :data-open="contextOpen"
      :aria-label="contextLabel"
    >
      <button
        type="button"
        class="immersive-workspace-shell__context-close"
        aria-label="关闭研究上下文"
        @click="emit('closeContext')"
      >
        <img :src="xMarkIcon" alt="">
      </button>
      <slot name="context" />
    </aside>

    <footer class="immersive-workspace-shell__dock" aria-label="论文决策操作">
      <slot name="dock" />
    </footer>
  </section>
</template>

<style scoped>
.immersive-workspace-shell {
  position: relative;
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-columns: 68px minmax(0, 1fr) 336px;
  padding-bottom: 88px;
  overflow: hidden;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.immersive-workspace-shell__rail {
  display: flex;
  min-height: 0;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 16px 7px;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-card);
}

.immersive-workspace-shell__document,
.immersive-workspace-shell__context {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.immersive-workspace-shell__document,
.immersive-workspace-shell__context {
  background: var(--color-bg-card);
}

.immersive-workspace-shell__context {
  position: relative;
  border-left: 1px solid var(--color-border);
}

.immersive-workspace-shell__context-close,
.immersive-workspace-shell__backdrop {
  display: none;
}

.immersive-workspace-shell__dock {
  position: absolute;
  z-index: 5;
  right: 100px;
  bottom: 0;
  left: 100px;
  padding: 10px 72px;
  border-top: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-card) 95%, transparent);
  box-shadow: 0 -8px 22px color-mix(in srgb, #000 7%, transparent);
}

@media (max-width: 1279px) {
  .immersive-workspace-shell {
    grid-template-columns: 58px minmax(0, 1fr);
  }

  .immersive-workspace-shell__context {
    position: absolute;
    z-index: 20;
    top: 0;
    right: 0;
    bottom: 88px;
    width: min(336px, calc(100% - 58px));
    visibility: hidden;
    transform: translateX(100%);
    box-shadow: -16px 0 36px color-mix(in srgb, #000 14%, transparent);
    transition: transform 180ms ease, visibility 180ms ease;
  }

  .immersive-workspace-shell__context--open {
    visibility: visible;
    transform: translateX(0);
  }

  .immersive-workspace-shell__context-close {
    position: sticky;
    z-index: 2;
    top: 10px;
    left: calc(100% - 42px);
    display: inline-flex;
    width: 32px;
    height: 32px;
    align-items: center;
    justify-content: center;
    margin: 10px 10px -42px 0;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    background: var(--color-bg-card);
    cursor: pointer;
  }

  .immersive-workspace-shell__context-close img {
    width: 16px;
    height: 16px;
  }

  .immersive-workspace-shell__backdrop {
    position: absolute;
    z-index: 19;
    inset: 0 0 88px 58px;
    display: block;
    border: 0;
    background: color-mix(in srgb, #000 24%, transparent);
    cursor: default;
  }

  .immersive-workspace-shell__dock {
    right: 24px;
    left: 82px;
    padding-inline: 34px;
  }
}

@media (max-width: 767px) {
  .immersive-workspace-shell {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 48px minmax(0, 1fr);
    padding-bottom: 72px;
  }

  .immersive-workspace-shell__rail {
    flex-direction: row;
    gap: 4px;
    padding: 5px 8px;
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }

  .immersive-workspace-shell__context {
    top: 48px;
    bottom: 72px;
    width: min(100%, 390px);
  }

  .immersive-workspace-shell__backdrop {
    inset: 48px 0 72px;
  }

  .immersive-workspace-shell__dock {
    right: 0;
    left: 0;
    padding: 7px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .immersive-workspace-shell__context {
    transition: none;
  }
}

:global(.dark) .immersive-workspace-shell__context-close img {
  filter: invert(1);
}
</style>
