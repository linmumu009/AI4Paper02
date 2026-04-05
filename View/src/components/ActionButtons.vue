<script setup lang="ts">
defineEmits<{
  undo: []
  skip: []
  superlike: []
  like: []
  detail: []
}>()
</script>

<template>
  <div class="flex items-end justify-center gap-2 sm:gap-3 py-3 sm:py-4">
    <!-- Undo -->
    <div class="flex flex-col items-center gap-1">
      <button
        class="w-10 h-10 sm:w-12 sm:h-12 rounded-full border-2 border-tinder-gold/40 flex items-center justify-center text-tinder-gold hover:bg-tinder-gold/10 hover:border-tinder-gold hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
        title="撤回"
        @click="$emit('undo')"
      >
        <svg width="17" height="17" class="sm:hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
        <svg width="20" height="20" class="hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
      </button>
      <span class="text-[10px] leading-none text-tinder-gold/70 select-none">撤回</span>
    </div>

    <!-- Skip / Nope -->
    <div class="flex flex-col items-center gap-1">
      <button
        class="w-12 h-12 sm:w-14 sm:h-14 rounded-full border-2 border-tinder-pink/40 flex items-center justify-center text-tinder-pink hover:bg-tinder-pink/10 hover:border-tinder-pink hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
        title="跳过"
        @click="$emit('skip')"
      >
        <svg width="22" height="22" class="sm:hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        <svg width="26" height="26" class="hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <span class="text-[10px] leading-none text-tinder-pink/70 select-none">跳过</span>
    </div>

    <!-- Detail -->
    <div class="flex flex-col items-center gap-1">
      <button
        class="w-10 h-10 sm:w-12 sm:h-12 rounded-full border-2 border-tinder-blue/40 flex items-center justify-center text-tinder-blue hover:bg-tinder-blue/10 hover:border-tinder-blue hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
        title="查看详情"
        @click="$emit('detail')"
      >
        <svg width="17" height="17" class="sm:hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <svg width="20" height="20" class="hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      </button>
      <span class="text-[10px] leading-none text-tinder-blue/70 select-none">详情</span>
    </div>

    <!-- Like / Save to KB -->
    <div class="flex flex-col items-center gap-1">
      <button
        class="w-12 h-12 sm:w-14 sm:h-14 rounded-full border-2 border-tinder-green/40 flex items-center justify-center text-tinder-green hover:bg-tinder-green/10 hover:border-tinder-green hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
        title="收藏到知识库"
        @click="$emit('like')"
      >
        <svg width="22" height="22" class="sm:hidden" viewBox="0 0 24 24" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
        <svg width="26" height="26" class="hidden sm:block" viewBox="0 0 24 24" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
      </button>
      <span class="text-[10px] leading-none text-tinder-green/70 select-none">收藏</span>
    </div>

    <!-- Open PDF -->
    <div class="flex flex-col items-center gap-1">
      <button
        class="w-10 h-10 sm:w-12 sm:h-12 rounded-full border-2 border-tinder-purple/40 flex items-center justify-center text-tinder-purple hover:bg-tinder-purple/10 hover:border-tinder-purple hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
        title="打开 PDF 原文"
        @click="$emit('superlike')"
      >
        <svg width="17" height="17" class="sm:hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <svg width="20" height="20" class="hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      </button>
      <span class="text-[10px] leading-none text-tinder-purple/70 select-none">PDF</span>
    </div>
  </div>
</template>
