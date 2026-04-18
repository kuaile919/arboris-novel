<template>
  <div class="min-h-screen p-4 md:p-8 md-surface-dim">
    <div class="max-w-5xl mx-auto">
      <div class="flex items-center justify-between mb-6">
        <button class="md-btn md-btn-text md-ripple" @click="goBack">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          返回
        </button>
        <button class="md-btn md-btn-filled md-ripple" :disabled="isSaving" @click="saveLibrary">
          {{ isSaving ? '保存中...' : '保存风格库' }}
        </button>
      </div>

      <div class="md-card md-card-elevated p-6 mb-6" style="border-radius: var(--md-radius-xl);">
        <h1 class="md-headline-medium mb-2" style="color: var(--md-on-surface);">写作风格库</h1>
        <p class="md-body-medium" style="color: var(--md-on-surface-variant);">
          风格规则跟随当前账号生效。每行一条规则，支持后续在生成流程中自动注入。
        </p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="md-card md-card-outlined p-6" style="border-radius: var(--md-radius-xl);">
          <h2 class="md-title-large mb-3" style="color: var(--md-primary);">大纲写作风格</h2>
          <p class="md-body-small mb-3" style="color: var(--md-on-surface-variant);">
            会注入到大纲预览与大纲生成提示词中。
          </p>
          <textarea
            v-model="outlineText"
            class="w-full p-3 rounded-lg border min-h-[320px]"
            style="border-color: var(--md-outline-variant); background-color: var(--md-surface); color: var(--md-on-surface);"
            placeholder="例如：\n- 每章大纲必须给出明确冲突与目标\n- 每3章至少推进一次主线"
          />
        </div>

        <div class="md-card md-card-outlined p-6" style="border-radius: var(--md-radius-xl);">
          <h2 class="md-title-large mb-3" style="color: var(--md-success);">章节写作风格</h2>
          <p class="md-body-small mb-3" style="color: var(--md-on-surface-variant);">
            会注入到章节正文生成提示词中；分层优化的“保存到风格库”也会自动入库到这里。
          </p>
          <textarea
            v-model="chapterText"
            class="w-full p-3 rounded-lg border min-h-[320px]"
            style="border-color: var(--md-outline-variant); background-color: var(--md-surface); color: var(--md-on-surface);"
            placeholder="例如：\n- 对话尽量短句，避免解释性台词\n- 每段动作后补一个感官细节"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NovelAPI } from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'

const router = useRouter()
const isSaving = ref(false)
const outlineText = ref('')
const chapterText = ref('')

const goBack = () => {
  router.push('/')
}

const loadLibrary = async () => {
  try {
    const data = await NovelAPI.getWritingStyleLibrary()
    outlineText.value = data.outline_text || ''
    chapterText.value = data.chapter_text || ''
  } catch (error: any) {
    console.error('加载写作风格库失败:', error)
    globalAlert.showError(error.message || '加载写作风格库失败')
  }
}

const saveLibrary = async () => {
  isSaving.value = true
  try {
    const data = await NovelAPI.updateWritingStyleLibrary(outlineText.value, chapterText.value)
    outlineText.value = data.outline_text || ''
    chapterText.value = data.chapter_text || ''
    globalAlert.showSuccess('写作风格库已保存')
  } catch (error: any) {
    console.error('保存写作风格库失败:', error)
    globalAlert.showError(error.message || '保存写作风格库失败')
  } finally {
    isSaving.value = false
  }
}

onMounted(loadLibrary)
</script>
