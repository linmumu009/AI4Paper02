<script setup lang="ts">
defineProps<{
  title?: string
  message: string
  showLoginCta?: boolean
}>()

const emit = defineEmits<{
  (e: 'login'): void
}>()
</script>

<template>
  <div class="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
    <!-- Icon card -->
    <div class="w-20 h-20 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center shadow-sm">
      <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-text-muted">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    </div>

    <!-- Text -->
    <div>
      <h2 class="text-lg font-bold text-text-primary mb-1.5">{{ title ?? '查看受限' }}</h2>
      <p class="text-sm text-text-secondary leading-relaxed">{{ message }}</p>
    </div>

    <!-- CTA -->
    <template v-if="showLoginCta">
      <button type="button" class="btn-primary max-w-[240px]" @click="emit('login')">
        登录后继续
      </button>
      <p class="text-xs text-text-muted -mt-2">免费账号即可查看更多内容</p>
    </template>
    <template v-else>
      <p class="text-xs text-text-muted">升级 Pro 账号可获得更多配额</p>
    </template>
  </div>
</template>
