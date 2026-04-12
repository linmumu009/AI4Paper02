<script setup lang="ts">
withDefaults(defineProps<{
  message: string
  /** 'proxy' shows proxy hint, 'server' shows server hint, else just shows message */
  type?: 'proxy' | 'server' | 'unknown'
  retryLabel?: string
}>(), {
  retryLabel: '重试',
})

defineEmits<{ retry: [] }>()
</script>

<!--
  Standard error state with optional retry action.
  Usage:
    <ErrorState :message="error" :type="errorType" @retry="loadData" />
-->
<template>
  <div class="flex flex-col items-center gap-3 text-center px-8">
    <span class="text-tinder-pink text-lg">{{ message }}</span>
    <p v-if="type === 'proxy'" class="text-sm text-text-muted max-w-xs">
      检测到系统代理可能未启动，请关闭代理程序（如 Clash / V2Ray）或确保代理正常运行后重试
    </p>
    <p v-else-if="type === 'server'" class="text-sm text-text-muted">
      服务端出现异常，请稍后再试
    </p>
    <slot />
    <button
      class="px-4 py-2 rounded-full bg-brand-gradient text-white text-sm font-medium cursor-pointer border-none hover:opacity-90 transition-opacity"
      @click="$emit('retry')"
    >
      {{ retryLabel }}
    </button>
  </div>
</template>
