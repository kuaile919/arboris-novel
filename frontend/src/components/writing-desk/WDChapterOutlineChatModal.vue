<template>
  <div v-if="show" class="md-dialog-overlay" @click.self="handleClose">
    <div class="md-dialog w-full max-w-2xl p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold">章节大纲对话修改</h3>
        <button type="button" class="md-icon-btn" @click="handleClose">×</button>
      </div>

      <p class="mb-2 text-sm text-gray-600">
        章节：第{{ chapter?.chapter_number ?? '-' }}章 {{ chapter?.title ?? '' }}
      </p>
      <p class="mb-4 text-sm text-gray-600">该功能正在整理中，当前为可用占位版本。</p>

      <div class="flex justify-end gap-2">
        <button type="button" class="md-btn md-btn-tonal" @click="handleClose">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChapterOutline } from '@/api/novel'

interface Props {
  show: boolean
  projectId: string
  chapter: ChapterOutline | null
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', updatedChapter: ChapterOutline): void
}>()

const handleClose = () => {
  emit('close')
}
</script>
