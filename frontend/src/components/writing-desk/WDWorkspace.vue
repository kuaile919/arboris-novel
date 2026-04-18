<!-- AIMETA P=写作台工作区_主编辑区域|R=章节编辑_生成|NR=不含侧边栏|E=component:WDWorkspace|X=ui|A=工作区|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="flex-1 min-w-0 h-full">
    <div class="md-card md-card-elevated h-full flex flex-col" style="border-radius: var(--md-radius-xl);">
      <!-- 章节工作区头部 -->
      <div v-if="selectedChapterNumber" class="md-card-header flex-shrink-0">
        <div class="flex items-center justify-between">
          <div>
            <div class="flex items-center gap-3 mb-2">
              <h2 class="md-title-large font-semibold">第{{ selectedChapterNumber }}章</h2>
              <span
                :class="[
                  'md-chip',
                  isChapterCompleted(selectedChapterNumber)
                    ? 'm3-chip-success'
                    : 'm3-chip-neutral'
                ]"
              >
                {{ isChapterCompleted(selectedChapterNumber) ? '已完成' : '未完成' }}
              </span>
            </div>
            <h3 class="md-title-medium md-on-surface mb-1">{{ selectedChapterOutline?.title || '未知标题' }}</h3>
            <p class="md-body-small md-on-surface-variant">{{ selectedChapterOutline?.summary || '暂无章节描述' }}</p>
            <p
              v-if="selectedChapterOutline?.foreshadowing?.payoff?.length"
              class="md-body-small md-on-surface-variant mt-1"
            >
              回收伏笔：{{ selectedChapterOutline.foreshadowing.payoff.join('；') }}
            </p>
          </div>
        </div>
      </div>

      <!-- 章节内容展示区 -->
      <div class="md-card-content flex-1 overflow-y-auto">
        <component
          :is="currentComponent"
          v-bind="currentComponentProps"
          @hideVersionSelector="$emit('hideVersionSelector')"
          @update:selectedVersionIndex="$emit('update:selectedVersionIndex', $event)"
          @showVersionDetail="$emit('showVersionDetail', $event)"
          @confirmVersionSelection="$emit('confirmVersionSelection')"
          @generateChapter="$emit('generateChapter', $event)"
          @showVersionSelector="$emit('showVersionSelector')"
          @regenerateChapter="confirmRegenerateChapter"
          @cancelGeneration="$emit('cancelChapterGeneration')"
          @evaluateChapter="$emit('evaluateChapter')"
          @showEvaluationDetail="$emit('showEvaluationDetail')"
          @openEditModal="openEditModal"
        />
      </div>
    </div>

    <!-- 编辑章节内容模态框 -->
    <div v-if="showEditModal" class="md-dialog-overlay">
      <div class="md-dialog w-full h-full max-w-5xl m3-editor-dialog">
        <!-- 模态框头部 -->
        <div class="flex items-center justify-between p-6 border-b" style="border-bottom-color: var(--md-outline-variant);">
          <h3 class="md-title-large font-semibold">
            编辑第{{ selectedChapterNumber }}章内容
          </h3>
          <button
            @click="closeEditModal"
            class="md-icon-btn md-ripple"
          >
            <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
            </svg>
          </button>
        </div>

        <!-- 模态框内容 -->
        <div class="flex-1 p-6 overflow-hidden">
          <div class="flex flex-col h-full">
            <div class="flex flex-col gap-4 mb-4">
              <div class="flex flex-wrap items-center gap-3">
                <label class="flex items-center gap-1 cursor-pointer select-none md-body-small md-on-surface-variant">
                  <input v-model="lockMasterScroll" type="checkbox" class="cursor-pointer" />
                  <span>锁定主列跟随</span>
                </label>
                <template v-if="lockMasterScroll">
                  <label class="flex items-center gap-1 cursor-pointer select-none md-body-small md-on-surface-variant">
                    <input v-model="masterScrollColumn" type="radio" value="left" class="cursor-pointer" />
                    <span>主列：左侧当前文</span>
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer select-none md-body-small md-on-surface-variant">
                    <input v-model="masterScrollColumn" type="radio" value="right" class="cursor-pointer" />
                    <span>主列：右侧参考稿</span>
                  </label>
                </template>
              </div>
              <p class="md-body-small md-on-surface-variant">
                左侧是手动编辑区，右侧展示 AI 备选版本供复制参考（右侧只读，可直接选中文本后复制粘贴到左侧）。
              </p>
            </div>
            <div class="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div class="min-h-0 flex flex-col">
                <div class="md-body-small md-on-surface-variant mb-2">当前文（可编辑）</div>
                <textarea
                  ref="leftEditorEl"
                  v-model="editingContent"
                  class="md-textarea flex-1 w-full resize-none"
                  placeholder="请输入章节内容..."
                  :disabled="isSaving"
                  @scroll="handleSyncScroll('left')"
                ></textarea>
              </div>
              <div class="min-h-0 flex flex-col">
                <div class="md-body-small md-on-surface-variant mb-2">AI 备选版本（只读参考）</div>
                <textarea
                  ref="rightReferenceEl"
                  :value="referenceContent"
                  class="md-textarea flex-1 w-full resize-none"
                  readonly
                  @scroll="handleSyncScroll('right')"
                ></textarea>
                <div v-if="!referenceContent.trim()" class="md-body-small md-on-surface-variant mt-2">
                  暂无可用的另一版本参考稿。
                </div>
              </div>
            </div>
            <div class="md-body-small md-on-surface-variant mt-3">
              左侧字数统计: {{ editingContent.length }}
            </div>
          </div>
        </div>

        <!-- 模态框底部 -->
        <div class="flex items-center justify-end gap-3 p-6 border-t" style="border-top-color: var(--md-outline-variant);">
          <button
            @click="closeEditModal"
            :disabled="isSaving"
            class="md-btn md-btn-outlined md-ripple disabled:opacity-50"
          >
            取消
          </button>
          <button
            @click="saveEditedContent"
            :disabled="isSaving || !editingContent.trim()"
            class="md-btn md-btn-filled md-ripple disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="isSaving" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
            </svg>
            {{ isSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import type { Chapter, ChapterOutline, ChapterGenerationResponse, ChapterVersion, NovelProject } from '@/api/novel'
import WorkspaceInitial from './workspace/WorkspaceInitial.vue'
import ChapterGenerating from './workspace/ChapterGenerating.vue'
import VersionSelector from './workspace/VersionSelector.vue'
import ChapterContent from './workspace/ChapterContent.vue'
import ChapterFailed from './workspace/ChapterFailed.vue'
import ChapterEmpty from './workspace/ChapterEmpty.vue'

interface Props {
  project: NovelProject | null
  selectedChapterNumber: number | null
  generatingChapter: number | null
  evaluatingChapter: number | null
  showVersionSelector: boolean
  chapterGenerationResult: ChapterGenerationResponse | null
  selectedVersionIndex: number
  availableVersions: ChapterVersion[]
  isSelectingVersion?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits([
  'regenerateChapter',
  'evaluateChapter',
  'hideVersionSelector',
  'update:selectedVersionIndex',
  'showVersionDetail',
  'confirmVersionSelection',
  'generateChapter',
  'showVersionSelector',
  'showEvaluationDetail',
  'fetchChapterStatus',
  'editChapter',
  'cancelChapterGeneration'
])

const confirmRegenerateChapter = async () => {
  const confirmed = await globalAlert.showConfirm('重新生成会覆盖当前章节的现有内容，确定继续吗？', '重新生成确认')
  if (confirmed) {
    emit('regenerateChapter')
  }
}

// 编辑模态框状态
const showEditModal = ref(false)
const editingContent = ref('')
const referenceContent = ref('')
const isSaving = ref(false)
const leftEditorEl = ref<HTMLTextAreaElement | null>(null)
const rightReferenceEl = ref<HTMLTextAreaElement | null>(null)
const ignoreNextScrollFrom = ref<'left' | 'right' | null>(null)
const lockMasterScroll = ref(true)
const masterScrollColumn = ref<'left' | 'right'>('left')

// 清理版本内容的辅助函数
const cleanVersionContent = (content: string): string => {
  if (!content) return ''
  try {
    const parsed = JSON.parse(content)
    const extractContent = (value: any): string | null => {
      if (!value) return null
      if (typeof value === 'string') return value
      if (Array.isArray(value)) {
        for (const item of value) {
          const nested = extractContent(item)
          if (nested) return nested
        }
        return null
      }
      if (typeof value === 'object') {
        for (const key of ['content', 'chapter_content', 'chapter_text', 'text', 'body', 'story']) {
          if (value[key]) {
            const nested = extractContent(value[key])
            if (nested) return nested
          }
        }
      }
      return null
    }
    const extracted = extractContent(parsed)
    if (extracted) {
      content = extracted
    }
  } catch (error) {
    // not a json
  }
  let cleaned = content.replace(/^"|"$/g, '')
  cleaned = cleaned.replace(/\\n/g, '\n')
  cleaned = cleaned.replace(/\\"/g, '"')
  cleaned = cleaned.replace(/\\t/g, '\t')
  cleaned = cleaned.replace(/\\\\/g, '\\')
  return cleaned
}

const findAlternativeVersionContent = (currentContent: string): string | null => {
  if (Array.isArray(props.availableVersions) && props.availableVersions.length > 0) {
    for (const version of props.availableVersions) {
      const candidate = cleanVersionContent(version?.content || '')
      if (!candidate.trim()) continue
      if (candidate.trim() !== currentContent.trim()) {
        return candidate
      }
    }
  }

  const versions = selectedChapter.value?.versions
  if (!Array.isArray(versions) || versions.length === 0) {
    return null
  }

  for (const version of versions) {
    const candidate = cleanVersionContent(version || '')
    if (!candidate.trim()) continue
    if (candidate.trim() !== currentContent.trim()) {
      return candidate
    }
  }

  return null
}

const openEditModal = () => {
  if (selectedChapter.value?.content) {
    const currentContent = cleanVersionContent(selectedChapter.value.content)
    editingContent.value = currentContent
    referenceContent.value = findAlternativeVersionContent(currentContent) || ''
    showEditModal.value = true
  }
}

const closeEditModal = () => {
  showEditModal.value = false
  editingContent.value = ''
  referenceContent.value = ''
  isSaving.value = false
  ignoreNextScrollFrom.value = null
}

const handleSyncScroll = (source: 'left' | 'right') => {
  if (lockMasterScroll.value && source !== masterScrollColumn.value) {
    return
  }

  if (ignoreNextScrollFrom.value === source) {
    ignoreNextScrollFrom.value = null
    return
  }

  const sourceEl = source === 'left' ? leftEditorEl.value : rightReferenceEl.value
  const targetEl = source === 'left' ? rightReferenceEl.value : leftEditorEl.value
  const targetKey: 'left' | 'right' = source === 'left' ? 'right' : 'left'

  if (!sourceEl || !targetEl) return

  const sourceMax = sourceEl.scrollHeight - sourceEl.clientHeight
  const targetMax = targetEl.scrollHeight - targetEl.clientHeight
  const ratio = sourceMax > 0 ? sourceEl.scrollTop / sourceMax : 0

  ignoreNextScrollFrom.value = targetKey
  targetEl.scrollTop = targetMax > 0 ? ratio * targetMax : 0
}

const saveEditedContent = async () => {
  if (!props.selectedChapterNumber || !editingContent.value.trim()) return
  
  isSaving.value = true
  try {
    emit('editChapter', {
      chapterNumber: props.selectedChapterNumber,
      content: editingContent.value
    })
    closeEditModal()
  } catch (error) {
    console.error('保存章节内容失败:', error)
  } finally {
    isSaving.value = false
  }
}

const selectedChapter = computed(() => {
  if (!props.project || props.selectedChapterNumber === null) return null
  return props.project.chapters.find(ch => ch.chapter_number === props.selectedChapterNumber) || null
})

const selectedChapterOutline = computed(() => {
  if (!props.project?.blueprint?.chapter_outline || props.selectedChapterNumber === null) return null
  return props.project.blueprint.chapter_outline.find(ch => ch.chapter_number === props.selectedChapterNumber) || null
})

const isChapterCompleted = (chapterNumber: number) => {
  if (!props.project?.chapters) return false
  const chapter = props.project.chapters.find(ch => ch.chapter_number === chapterNumber)
  return chapter && chapter.generation_status === 'successful'
}

const isChapterGenerating = (chapterNumber: number) => {
  if (!props.project?.chapters) return false
  const chapter = props.project.chapters.find(ch => ch.chapter_number === chapterNumber)
  return chapter && chapter.generation_status === 'generating'
}

const isChapterFailed = (chapterNumber: number) => {
  if (!props.project?.chapters) return false
  const chapter = props.project.chapters.find(ch => ch.chapter_number === chapterNumber)
  return chapter && chapter.generation_status === 'failed'
}

const isChapterEvaluationFailed = (chapterNumber: number) => {
  if (!props.project?.chapters) return false
  const chapter = props.project.chapters.find(ch => ch.chapter_number === chapterNumber)
  return chapter && chapter.generation_status === 'evaluation_failed'
}

const canGenerateChapter = (chapterNumber: number | null) => {
  if (chapterNumber === null || !props.project?.blueprint?.chapter_outline) return false

  const outlines = props.project.blueprint.chapter_outline.sort((a, b) => a.chapter_number - b.chapter_number)
  
  for (const outline of outlines) {
    if (outline.chapter_number >= chapterNumber) break
    
    const chapter = props.project?.chapters.find(ch => ch.chapter_number === outline.chapter_number)
    if (!chapter || chapter.generation_status !== 'successful') {
      return false
    }
  }

  const currentChapter = props.project?.chapters.find(ch => ch.chapter_number === chapterNumber)
  if (currentChapter && currentChapter.generation_status === 'successful') {
    return true
  }

  return true
}

const currentComponent = computed(() => {
  if (!props.selectedChapterNumber) {
    return WorkspaceInitial
  }

  const status = selectedChapter.value?.generation_status
  if (status === 'generating' || status === 'evaluating' || status === 'selecting') {
    return ChapterGenerating // Use a generic "in-progress" component
  }

  if (status === 'waiting_for_confirm' || status === 'evaluation_failed') {
    return VersionSelector
  }

  if (selectedChapter.value?.content) {
    return ChapterContent
  }
  if (isChapterFailed(props.selectedChapterNumber)) {
    return ChapterFailed
  }
  return ChapterEmpty
})

// Polling for chapter status updates
const pollingTimer = ref<number | null>(null)

const startPolling = () => {
  stopPolling()
  pollingTimer.value = window.setInterval(() => {
    emit('fetchChapterStatus')
  }, 10000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

watch(
  () => [selectedChapter.value?.generation_status, props.evaluatingChapter, props.isSelectingVersion, props.selectedChapterNumber],
  ([status, evaluating, selecting, chapterNumber]) => {
    if (chapterNumber === null) {
      stopPolling()
      return
    }

    const isEvaluating = evaluating === chapterNumber
    // Poll when generating, evaluating, or selecting a version
    const needsPolling = status === 'generating' || status === 'evaluating' || status === 'selecting'

    if (needsPolling) {
      startPolling()
    } else {
      stopPolling()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  stopPolling()
})

const currentComponentProps = computed(() => {
  if (!props.selectedChapterNumber) {
    return {}
  }
  const status = selectedChapter.value?.generation_status
  if (status === 'generating' || status === 'evaluating' || status === 'selecting') {
    return {
      chapterNumber: props.selectedChapterNumber,
      status: status
    }
  }

  if (status === 'waiting_for_confirm' || status === 'evaluation_failed') {
    return {
      selectedChapter: selectedChapter.value,
      chapterGenerationResult: props.chapterGenerationResult,
      availableVersions: props.availableVersions,
      selectedVersionIndex: props.selectedVersionIndex,
      isSelectingVersion: props.isSelectingVersion,
      evaluatingChapter: props.evaluatingChapter,
      isEvaluationFailed: isChapterEvaluationFailed(props.selectedChapterNumber)
    }
  }
  if (selectedChapter.value?.content) {
    return { 
      selectedChapter: selectedChapter.value,
      projectId: props.project?.id
    }
  }
  if (isChapterFailed(props.selectedChapterNumber)) {
    return {
      chapterNumber: props.selectedChapterNumber,
      generatingChapter: props.generatingChapter
    }
  }
  return {
    chapterNumber: props.selectedChapterNumber,
    generatingChapter: props.generatingChapter,
    canGenerate: canGenerateChapter(props.selectedChapterNumber)
  }
})
</script>

<style scoped>
.m3-chip-success {
  background-color: var(--md-success-container);
  color: var(--md-on-success-container);
}

.m3-chip-neutral {
  background-color: var(--md-surface-container);
  color: var(--md-on-surface-variant);
}

.m3-editor-dialog {
  max-width: min(1200px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}
</style>
