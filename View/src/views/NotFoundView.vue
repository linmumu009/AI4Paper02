<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const missingPath = computed(() => route.fullPath)
</script>

<template>
  <div class="h-full overflow-y-auto bg-bg px-5 py-10 sm:px-8">
    <section class="mx-auto flex min-h-full max-w-2xl items-center justify-center">
      <div class="w-full rounded-3xl border border-border bg-bg-card p-7 text-center shadow-2xl sm:p-10">
        <div
          class="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-tinder-pink/10 text-2xl"
          aria-hidden="true"
        >
          🧭
        </div>
        <p class="mb-2 text-sm font-semibold text-tinder-pink">404 · 页面未找到</p>
        <h1 class="text-2xl font-bold text-text-primary sm:text-3xl">这个研究入口不存在或已经移动</h1>
        <p class="mx-auto mt-4 max-w-lg text-sm leading-6 text-text-secondary">
          没有找到 <code class="rounded bg-bg-elevated px-1.5 py-0.5 text-text-primary">{{ missingPath }}</code>。
          你可以返回论文发现页，或直接打开知识库继续研究。
        </p>

        <div class="mt-7 flex flex-wrap items-center justify-center gap-3">
          <router-link
            to="/"
            class="rounded-full bg-brand-gradient px-5 py-2.5 text-sm font-semibold text-white no-underline transition-opacity hover:opacity-90"
          >
            返回论文发现
          </router-link>
          <router-link
            to="/?tool=knowledge"
            class="rounded-full border border-border px-5 py-2.5 text-sm font-medium text-text-secondary no-underline transition-colors hover:border-border-light hover:text-text-primary"
          >
            打开知识库
          </router-link>
          <router-link
            to="/tutorial"
            class="rounded-full px-4 py-2.5 text-sm font-medium text-text-muted no-underline transition-colors hover:text-text-primary"
          >
            查看使用教程
          </router-link>
        </div>
      </div>
    </section>
  </div>
</template>
