<!-- AIMETA P=评审详情弹窗_章节评审展示|R=评审结果展示|NR=不含评审逻辑|E=component:WDEvaluationDetailModal|X=ui|A=评审弹窗|D=vue|S=dom|RD=./README.ai -->
<template>
  <div v-if="show" class="md-dialog-overlay">
    <div class="md-dialog w-full max-w-4xl m3-eval-dialog flex flex-col">
      <!-- 弹窗头部 -->
      <div class="flex items-center justify-between p-6 border-b" style="border-bottom-color: var(--md-outline-variant);">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style="background-color: var(--md-secondary);">
                <svg class="w-6 h-6" style="color: var(--md-on-secondary);" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M10 2a6 6 0 00-6 6v3.586l-1.707 1.707A1 1 0 003 15v1a1 1 0 001 1h12a1 1 0 001-1v-1a1 1 0 00-.293-.707L16 11.586V8a6 6 0 00-6-6zM8.05 17a2 2 0 103.9 0H8.05z"></path>
                </svg>
            </div>
            <h3 class="md-headline-small font-semibold">AI 评审详情</h3>
        </div>
        <button
          @click="$emit('close')"
          class="md-icon-btn md-ripple"
        >
          <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>

      <!-- 弹窗内容 -->
      <div class="p-6 overflow-y-auto max-h-[calc(80vh-130px)]">
        <div v-if="parsedEvaluation" class="space-y-6 text-sm">
            <div class="md-card md-card-filled p-4" style="border-radius: var(--md-radius-lg); background-color: var(--md-secondary-container);">
              <p class="md-title-small font-semibold" style="color: var(--md-on-secondary-container);">🏆 最佳选择：版本 {{ parsedEvaluation.best_choice }}</p>
              <p class="md-body-small mt-2" style="color: var(--md-on-secondary-container);">{{ parsedEvaluation.reason_for_choice }}</p>
            </div>
            <div class="space-y-4">
              <div v-for="(evalResult, versionName) in parsedEvaluation.evaluation" :key="versionName" class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-lg);">
                <h5 class="md-title-medium font-semibold mb-2">版本 {{ String(versionName).replace('version', '') }} 评估</h5>
                <div class="prose prose-sm max-w-none md-on-surface space-y-3">
                  <div>
                    <p class="font-semibold">综合评价:</p>
                    <p>{{ evalResult.overall_review }}</p>
                  </div>
                  <div>
                    <p class="font-semibold">优点:</p>
                    <ul class="list-disc pl-5 space-y-1">
                      <li v-for="(pro, i) in evalResult.pros" :key="`pro-${i}`">{{ pro }}</li>
                    </ul>
                  </div>
                  <div>
                    <p class="font-semibold">缺点:</p>
                    <ul class="list-disc pl-5 space-y-1">
                      <li v-for="(con, i) in evalResult.cons" :key="`con-${i}`">{{ con }}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div 
            v-else
            class="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0"
            style="color: var(--md-on-surface);"
            v-html="parseMarkdown(evaluation)"
          ></div>
      </div>

      <!-- 弹窗底部操作按钮 -->
      <div class="flex items-center justify-end p-6 border-t" style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
        <button
            @click="$emit('close')"
            class="md-btn md-btn-filled md-ripple"
        >
            关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  show: boolean
  evaluation: string | null
}

const props = defineProps<Props>()

defineEmits(['close'])

/**
 * 从 Markdown 代码块中提取 JSON 字符串
 */
const unwrapMarkdownJson = (rawText: string): string => {
  if (!rawText) return rawText
  const trimmed = rawText.trim()

  // 尝试匹配 ```json ... ``` 或 ``` ... ```
  const fenceMatch = trimmed.match(/```(?:json|JSON)?\s*([\s\S]*?)\s*```/)
  if (fenceMatch && fenceMatch[1]) {
    return fenceMatch[1].trim()
  }

  // 尝试找到 JSON 对象或数组
  const jsonStart = trimmed.search(/[{\[]/)
  if (jsonStart !== -1) {
    const closingBrace = trimmed.lastIndexOf('}')
    const closingBracket = trimmed.lastIndexOf(']')
    const endIdx = Math.max(closingBrace, closingBracket)
    if (endIdx !== -1 && endIdx > jsonStart) {
      return trimmed.slice(jsonStart, endIdx + 1).trim()
    }
  }

  return trimmed
}

/**
 * 修复常见的 JSON 格式错误
 */
const fixJsonString = (jsonStr: string): string => {
  if (!jsonStr) return jsonStr

  let result = jsonStr

  // 修复数组中带引号前缀的元素，如 `" "xxx"` -> `"xxx"`
  result = result.replace(/"(\s*)"([^"]+)"/g, '"$2"')

  // 修复字符串中未转义的换行符
  // 遍历字符串，跟踪是否在字符串内部
  const chars = result.split('')
  let inString = false
  let escapeNext = false
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i]
    if (escapeNext) {
      escapeNext = false
      continue
    }
    if (ch === '\\') {
      escapeNext = true
      continue
    }
    if (ch === '"') {
      inString = !inString
    } else if (inString && (ch === '\n' || ch === '\r')) {
      chars[i] = ch === '\n' ? '\\n' : '\\r'
    }
  }

  return chars.join('')
}

const parsedEvaluation = computed(() => {
  if (!props.evaluation) return null
  try {
    // 先去除 markdown 代码块包裹
    let cleanedJson = unwrapMarkdownJson(props.evaluation)

    // 尝试直接解析
    try {
      let data = JSON.parse(cleanedJson)
      if (typeof data === 'string') {
        data = JSON.parse(unwrapMarkdownJson(data))
      }
      return data
    } catch {
      // 直接解析失败，尝试修复后解析
      const fixedJson = fixJsonString(cleanedJson)
      let data = JSON.parse(fixedJson)
      if (typeof data === 'string') {
        data = JSON.parse(fixJsonString(unwrapMarkdownJson(data)))
      }
      return data
    }
  } catch (error) {
    console.error('Failed to parse evaluation JSON:', error)
    return null
  }
})

const parseMarkdown = (text: string | null): string => {
  if (!text) return ''
  let parsed = text
    .replace(/\\n/g, '\n')
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, '\\')
  parsed = parsed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  parsed = parsed.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  parsed = parsed.replace(
    /^([A-Z])\)\s*\*\*(.*?)\*\*(.*)/gm,
    '<div class="mb-2"><span class="inline-flex items-center justify-center w-6 h-6 text-sm font-bold rounded-full mr-2" style="background-color: var(--md-primary-container); color: var(--md-on-primary-container);">$1</span><strong>$2</strong>$3</div>'
  )
  parsed = parsed.replace(/\n/g, '<br>')
  parsed = parsed.replace(/(<br\s*\/?>\s*){2,}/g, '</p><p class="mt-2">')
  if (!parsed.includes('<p>')) {
    parsed = `<p>${parsed}</p>`
  }
  return parsed
}
</script>

<style scoped>
.m3-eval-dialog {
  max-width: min(960px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}
</style>
