<script setup lang="ts">
import arrowRightIcon from '../../assets/heroicons/arrow-right.svg'

const emit = defineEmits<{
  suggest: [question: string]
}>()

const suggestions = [
  {
    title: '这批论文的核心研究问题是什么？',
    desc: '提炼所有论文共同关注的科学问题与研究动机',
  },
  {
    title: '各论文的主要方法与技术路线有何异同？',
    desc: '横向对比实验设计、模型架构或分析框架',
  },
  {
    title: '这批研究的主要结论与局限性是什么？',
    desc: '汇总实验结果、性能指标及作者指出的不足',
  },
  {
    title: '未来研究方向和开放问题有哪些？',
    desc: '整合各论文对后续工作的展望与尚待解决的挑战',
  },
]
</script>

<template>
  <div class="w-full select-none">
    <p class="text-[11px] text-text-muted/50 uppercase tracking-wider mb-3">建议研究问题</p>
    <div class="space-y-1.5">
      <button
        v-for="s in suggestions"
        :key="s.title"
        class="w-full flex items-center justify-between px-4 py-3 rounded-xl hover:bg-bg-elevated/40 transition-all text-left group cursor-pointer"
        @click="emit('suggest', s.title)"
      >
        <span class="text-[13px] text-text-secondary group-hover:text-text-primary transition-colors leading-snug">{{ s.title }}</span>
        <img :src="arrowRightIcon" alt="" class="shrink-0 w-[13px] h-[13px] opacity-30 group-hover:opacity-60 transition-opacity ml-3">
      </button>
    </div>
  </div>
</template>

<style scoped>
:global(.dark) img { filter: invert(1); }
</style>
