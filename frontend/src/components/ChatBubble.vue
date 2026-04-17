<!-- AIMETA P=聊天气泡_对话消息展示|R=消息气泡|NR=不含输入功能|E=component:ChatBubble|X=internal|A=气泡组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div :class="wrapperClass">
    <div :class="bubbleClass">
      <!-- AI 消息支持 markdown 渲染 -->
      <div 
        v-if="type === 'ai' && shouldRenderAsPlainText"
        class="max-w-none whitespace-pre-wrap break-words text-[15px] leading-[1.9]"
      >{{ normalizedAiMessage }}</div>
      <div
        v-else-if="type === 'ai'" 
        class="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0"
        v-html="renderedMessage"
      ></div>
      <!-- 用户消息保持原样 -->
      <div v-else>{{ message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  message: string
  type: 'user' | 'ai'
}

const props = defineProps<Props>()

const decodeEscapedText = (text: string): string => {
  if (!text) return ''
  return text
    .replace(/\\n/g, '\n')
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, '\\')
}

const escapeHtml = (text: string): string => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// 简单的 markdown 解析函数
const parseMarkdown = (text: string): string => {
  if (!text) return ''

  let parsed = escapeHtml(decodeEscapedText(text))
  
  // 处理加粗文本 **text**
  parsed = parsed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  
  // 处理斜体文本 *text*
  parsed = parsed.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  
  // 处理选项列表 A) text
  parsed = parsed.replace(/^([A-Z])\)\s*\*\*(.*?)\*\*(.*)/gm, '<div class="mb-2"><span class="inline-flex items-center justify-center w-6 h-6 bg-indigo-100 text-indigo-600 text-sm font-bold rounded-full mr-2">$1</span><strong>$2</strong>$3</div>')
  
  // 处理普通换行
  parsed = parsed.replace(/\n/g, '<br>')
  
  // 处理多个连续的 <br> 标签为段落
  parsed = parsed.replace(/(<br\s*\/?>\s*){2,}/g, '</p><p class="mt-2">')
  
  // 包装在段落标签中
  if (!parsed.includes('<p>')) {
    parsed = `<p>${parsed}</p>`
  }
  
  return parsed
}

const decodedMessage = computed(() => decodeEscapedText(props.message))

const extractJsonLikeAiMessage = (text: string): string | null => {
  const normalized = text.trim()
  if (!normalized) return null

  try {
    const parsed = JSON.parse(normalized) as Record<string, unknown>
    const candidate = parsed?.ai_message ?? parsed?.message ?? parsed?.content
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim()
    }
  } catch {
    // ignore malformed json and continue with tolerant extraction
  }

  const patterns = [
    /"ai_message"\s*:\s*"([\s\S]*?)"\s*,\s*"proposed_patch"/,
    /"ai_message"\s*:\s*"([\s\S]*?)"\s*,\s*"need_confirm"/,
    /"message"\s*:\s*"([\s\S]*?)"\s*,\s*"proposed_patch"/,
  ]

  for (const pattern of patterns) {
    const match = normalized.match(pattern)
    const candidate = match?.[1]?.trim()
    if (candidate) {
      return candidate
    }
  }
  return null
}

const normalizedAiMessage = computed(() => {
  if (props.type !== 'ai') return decodedMessage.value
  const extracted = extractJsonLikeAiMessage(decodedMessage.value)
  return extracted ?? decodedMessage.value
})

const shouldRenderAsPlainText = computed(() => {
  if (props.type !== 'ai') return false
  const text = normalizedAiMessage.value.trim()
  if (!text) return false
  if (text.startsWith('{') || text.startsWith('[')) return true

  const jsonLikeKeys = text.match(/\"[a-zA-Z0-9_\u4e00-\u9fa5]+\"\s*:/g)
  return Boolean(jsonLikeKeys && jsonLikeKeys.length >= 2)
})

const renderedMessage = computed(() => {
  if (props.type === 'ai') {
    return parseMarkdown(normalizedAiMessage.value)
  }
  return props.message
})

const wrapperClass = computed(() => {
  return `w-full flex ${props.type === 'ai' ? 'justify-start' : 'justify-end'}`
})

const bubbleClass = computed(() => {
  const baseClass = 'max-w-md lg:max-w-lg p-4 rounded-lg shadow-md fade-in'
  const typeClass = props.type === 'ai' ? 'chat-bubble-ai' : 'chat-bubble-user'
  return `${baseClass} ${typeClass}`
})
</script>
