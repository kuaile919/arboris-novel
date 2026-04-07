<template>
  <div class="fade-in">
    <div v-if="loading || !uiControl" class="flex justify-center items-center p-4">
      <div class="loader"></div>
    </div>

    <div v-else-if="shouldShowChoices">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <button
          v-for="option in uiControl.options"
          :key="option.id"
          @click="handleOptionSelect(option.id, option.label)"
          class="p-3 bg-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-200 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          {{ option.label }}
        </button>
        <button
          v-if="shouldShowManualInputToggle"
          @click="isManualInput = true"
          class="p-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-gray-400"
        >
          我要输入
        </button>
      </div>

      <form
        v-if="shouldShowManualInputToggle"
        @submit.prevent="handleTextSubmit"
        class="flex items-center gap-3"
      >
        <textarea
          ref="textInputRef"
          v-model="textInput"
          :placeholder="isManualInput ? '请输入您的想法...' : '选择上方选项或点击“我要输入”'"
          class="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none transition-all disabled:bg-gray-100 resize-none overflow-y-auto leading-relaxed"
          :disabled="!isManualInput"
          rows="5"
          @input="handleTextareaInput"
        ></textarea>
        <button
          type="submit"
          class="flex-shrink-0 w-12 h-12 bg-indigo-500 rounded-full flex items-center justify-center hover:bg-indigo-600 transition-all shadow-md disabled:bg-gray-300"
          :disabled="!isManualInput"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="text-white"
          >
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </form>
    </div>

    <form
      v-else-if="shouldShowTextInput"
      @submit.prevent="handleTextSubmit"
      class="flex items-center gap-3"
    >
      <textarea
        ref="textInputRef"
        v-model="textInput"
        :placeholder="uiControl.placeholder || '请输入...'"
        class="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none transition-all resize-none overflow-y-auto leading-relaxed"
        required
        rows="5"
        @input="handleTextareaInput"
      ></textarea>
      <button
        type="submit"
        class="flex-shrink-0 w-12 h-12 bg-indigo-500 rounded-full flex items-center justify-center hover:bg-indigo-600 transition-all shadow-md"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="text-white"
        >
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
    </form>

    <div v-else class="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
      当前回复没有可交互选项，请刷新对话或重试上一轮输入。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import type { UIControl } from '@/api/novel'

interface Props {
  uiControl: UIControl | null
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  submit: [userInput: { id: string; value: string } | null]
}>()

const textInput = ref('')
const textInputRef = ref<HTMLTextAreaElement>()
const isManualInput = ref(false)

const MIN_ROWS = 5
const MAX_ROWS = 5

const shouldShowChoices = computed(() => {
  if (!props.uiControl) {
    return false
  }

  return (
    props.uiControl.type === 'single_choice' ||
    (Array.isArray(props.uiControl.options) && props.uiControl.options.length > 0)
  )
})

const shouldShowManualInputToggle = computed(() => props.uiControl?.type === 'single_choice')
const shouldShowTextInput = computed(() => props.uiControl?.type === 'text_input')

const adjustTextareaHeight = () => {
  const textarea = textInputRef.value
  if (!textarea || typeof window === 'undefined') {
    return
  }

  const lineHeight = parseFloat(window.getComputedStyle(textarea).lineHeight || '0') || 20
  const minHeight = lineHeight * MIN_ROWS
  const maxHeight = lineHeight * MAX_ROWS

  textarea.style.height = 'auto'
  const targetHeight = Math.min(maxHeight, Math.max(minHeight, textarea.scrollHeight))
  textarea.style.height = `${targetHeight}px`
}

const handleTextareaInput = () => {
  adjustTextareaHeight()
}

const handleOptionSelect = (id: string, label: string) => {
  emit('submit', { id, value: label })
}

const handleTextSubmit = () => {
  if (textInput.value.trim()) {
    emit('submit', { id: 'text_input', value: textInput.value.trim() })
    textInput.value = ''
    nextTick(() => adjustTextareaHeight())
  }
}

watch(
  () => props.uiControl,
  async newControl => {
    isManualInput.value = false
    textInput.value = ''

    await nextTick()
    adjustTextareaHeight()

    if (newControl?.type === 'text_input') {
      textInputRef.value?.focus()
    }
  },
  { deep: true }
)

watch(isManualInput, async newValue => {
  if (newValue) {
    await nextTick()
    adjustTextareaHeight()
    textInputRef.value?.focus()
  }
})
</script>
