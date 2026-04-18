<template>
  <div v-if="show" class="md-dialog-overlay" @click.self="handleClose">
    <div class="md-dialog w-full max-w-4xl p-0 overflow-hidden mx-3 sm:mx-0">
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <h3 class="text-lg font-semibold">章节大纲对话修改</h3>
        <button type="button" class="md-icon-btn" @click="handleClose">×</button>
      </div>

      <div class="px-6 py-3 text-sm text-gray-600 border-b border-gray-100 bg-gray-50">
        章节：第{{ chapter?.chapter_number ?? '-' }}章 {{ chapter?.title ?? '' }}
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] flex-1 min-h-0">
        <div
          ref="messageContainer"
          class="px-6 py-4 overflow-y-auto min-h-0 space-y-3 border-r border-gray-100"
        >
          <div v-if="isLoadingContext" class="text-sm text-gray-500">正在加载本章信息...</div>

          <div v-if="!isLoadingContext" class="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3">
            <div>
              <div class="text-xs text-gray-500 mb-1">当前标题</div>
              <div class="text-sm text-gray-900">{{ contextData?.title || chapter?.title || '-' }}</div>
            </div>
            <div>
              <div class="text-xs text-gray-500 mb-1">当前摘要</div>
              <div class="text-sm text-gray-900 whitespace-pre-wrap">{{ contextData?.summary || chapter?.summary || '-' }}</div>
            </div>
            <div v-if="contextData?.narrative_phase || contextData?.story_progress || contextData?.emotion_hook" class="text-xs text-gray-600">
              <span v-if="contextData?.narrative_phase">叙事阶段：{{ contextData.narrative_phase }}</span>
              <span v-if="contextData?.story_progress" class="ml-3">进度：{{ contextData.story_progress }}</span>
              <span v-if="contextData?.emotion_hook" class="ml-3">情绪钩子：{{ contextData.emotion_hook }}</span>
            </div>
          </div>

          <div
            v-for="(msg, index) in messages"
            :key="`${msg.role}-${index}-${msg.content.slice(0, 16)}`"
            class="flex"
            :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="max-w-[88%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap"
              :class="msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-800'"
            >
              {{ msg.content }}
            </div>
          </div>

          <div v-if="latestProposedOutline" class="rounded-xl border border-blue-200 bg-blue-50 p-4">
            <div class="text-sm font-semibold text-blue-800 mb-2">建议大纲</div>
            <div class="text-xs text-blue-700 mb-1">标题</div>
            <div class="text-sm text-gray-900 mb-3">{{ latestProposedOutline.title }}</div>
            <div class="text-xs text-blue-700 mb-1">摘要</div>
            <div class="text-sm text-gray-900 whitespace-pre-wrap">{{ latestProposedOutline.summary }}</div>
          </div>
        </div>

        <div class="px-5 py-4 overflow-y-auto min-h-0 bg-white">
          <div class="text-sm font-semibold text-gray-800 mb-3">本章结构化信息</div>

          <div class="space-y-3 text-sm">
            <section>
              <h4 class="font-medium text-gray-700 mb-1">新增人物</h4>
              <div v-if="viewCharacters.length" class="space-y-1">
                <div v-for="(item, i) in viewCharacters" :key="`c-${i}`" class="text-gray-700">
                  {{ item.name }}<span v-if="item.description"> - {{ item.description }}</span>
                </div>
              </div>
              <div v-else class="text-gray-400">暂无</div>
            </section>

            <section>
              <h4 class="font-medium text-gray-700 mb-1">新增地点</h4>
              <div v-if="viewLocations.length" class="space-y-1">
                <div v-for="(item, i) in viewLocations" :key="`l-${i}`" class="text-gray-700">
                  {{ item.name }}<span v-if="item.description"> - {{ item.description }}</span>
                </div>
              </div>
              <div v-else class="text-gray-400">暂无</div>
            </section>

            <section>
              <h4 class="font-medium text-gray-700 mb-1">新增势力</h4>
              <div v-if="viewFactions.length" class="space-y-1">
                <div v-for="(item, i) in viewFactions" :key="`f-${i}`" class="text-gray-700">
                  {{ item.name }}<span v-if="item.description"> - {{ item.description }}</span>
                </div>
              </div>
              <div v-else class="text-gray-400">暂无</div>
            </section>

            <section>
              <h4 class="font-medium text-gray-700 mb-1">伏笔埋设（埋）</h4>
              <div v-if="viewPlants.length" class="space-y-1">
                <div v-for="(item, i) in viewPlants" :key="`p-${i}`" class="text-gray-700">
                  {{ item.content }}
                </div>
              </div>
              <div v-else class="text-gray-400">暂无</div>
            </section>

            <section>
              <h4 class="font-medium text-gray-700 mb-1">伏笔回收（收）</h4>
              <div v-if="viewPayoffs.length" class="space-y-1">
                <div v-for="(item, i) in viewPayoffs" :key="`po-${i}`" class="text-gray-700">
                  {{ item.content }}
                </div>
              </div>
              <div v-else class="text-gray-400">暂无</div>
            </section>
          </div>

          <div class="mt-5 flex justify-end">
            <button
              type="button"
              class="md-btn md-btn-filled"
              :disabled="isApplying || !latestProposedOutline"
              @click="applyProposedOutline"
            >
              {{ isApplying ? '保存中...' : '确认并保存' }}
            </button>
          </div>
        </div>
      </div>

      <div class="px-6 py-4 border-t border-gray-200 bg-gray-50">
        <div class="flex gap-2">
          <textarea
            v-model="userInput"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows="3"
            placeholder="例如：把这章结尾改成主角主动设局，不要被动挨打。"
            :disabled="isSending || !chapter"
            @keydown.ctrl.enter.prevent="sendMessage"
            @keydown.meta.enter.prevent="sendMessage"
          />
          <button
            type="button"
            class="md-btn md-btn-filled self-end"
            :disabled="isSending || !trimmedInput || !chapter"
            @click="sendMessage"
          >
            {{ isSending ? '发送中...' : '发送' }}
          </button>
        </div>
        <div class="mt-3 flex justify-end gap-2">
          <button type="button" class="md-btn md-btn-tonal" @click="handleClose">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { NovelAPI } from '@/api/novel'
import type {
  ChapterOutline,
  ChapterOutlineConverseContextResponse,
  OutlineEntityItem,
  OutlineForeshadowingItem,
} from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'

interface Props {
  show: boolean
  projectId: string
  chapter: ChapterOutline | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', updatedChapter: ChapterOutline): void
}>()

type ConverseMessage = {
  role: 'user' | 'assistant'
  content: string
}

type ProposedOutline = {
  title: string
  summary: string
}

type StructuredUpdates = {
  new_characters: OutlineEntityItem[]
  new_locations: OutlineEntityItem[]
  new_factions: OutlineEntityItem[]
  foreshadowing_plants: OutlineForeshadowingItem[]
  foreshadowing_payoffs: OutlineForeshadowingItem[]
}

const messageContainer = ref<HTMLElement | null>(null)
const messages = ref<ConverseMessage[]>([])
const userInput = ref('')
const isSending = ref(false)
const isApplying = ref(false)
const isLoadingContext = ref(false)
const contextData = ref<ChapterOutlineConverseContextResponse | null>(null)
const latestProposedOutline = ref<ProposedOutline | null>(null)
const latestUpdates = ref<StructuredUpdates>({
  new_characters: [],
  new_locations: [],
  new_factions: [],
  foreshadowing_plants: [],
  foreshadowing_payoffs: [],
})

const trimmedInput = computed(() => userInput.value.trim())

const viewCharacters = computed(() =>
  latestUpdates.value.new_characters.length
    ? latestUpdates.value.new_characters
    : (contextData.value?.new_characters || [])
)
const viewLocations = computed(() =>
  latestUpdates.value.new_locations.length
    ? latestUpdates.value.new_locations
    : (contextData.value?.new_locations || [])
)
const viewFactions = computed(() =>
  latestUpdates.value.new_factions.length
    ? latestUpdates.value.new_factions
    : (contextData.value?.new_factions || [])
)
const viewPlants = computed(() =>
  latestUpdates.value.foreshadowing_plants.length
    ? latestUpdates.value.foreshadowing_plants
    : (contextData.value?.foreshadowing_plants || [])
)
const viewPayoffs = computed(() =>
  latestUpdates.value.foreshadowing_payoffs.length
    ? latestUpdates.value.foreshadowing_payoffs
    : (contextData.value?.foreshadowing_payoffs || [])
)

const scrollToBottom = async () => {
  await nextTick()
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

const resetSession = () => {
  messages.value = []
  userInput.value = ''
  latestProposedOutline.value = null
  latestUpdates.value = {
    new_characters: [],
    new_locations: [],
    new_factions: [],
    foreshadowing_plants: [],
    foreshadowing_payoffs: [],
  }
}

const loadContext = async () => {
  if (!props.projectId || !props.chapter) return
  isLoadingContext.value = true
  try {
    contextData.value = await NovelAPI.getChapterOutlineConverseContext(
      props.projectId,
      props.chapter.chapter_number
    )
  } catch (error) {
    globalAlert.showError(`加载章节信息失败: ${error instanceof Error ? error.message : '未知错误'}`, '加载失败')
  } finally {
    isLoadingContext.value = false
  }
}

const sendMessage = async () => {
  if (!props.chapter || !trimmedInput.value || isSending.value) return

  const text = trimmedInput.value
  const historyPayload = messages.value.map(msg => ({ role: msg.role, content: msg.content }))

  userInput.value = ''
  messages.value.push({ role: 'user', content: text })
  isSending.value = true
  await scrollToBottom()

  try {
    const res = await NovelAPI.converseChapterOutline(
      props.projectId,
      props.chapter.chapter_number,
      text,
      historyPayload
    )
    const aiMessage = (res.ai_message || '').trim()
    if (aiMessage) {
      messages.value.push({ role: 'assistant', content: aiMessage })
    }
    if (res.proposed_outline?.title && res.proposed_outline?.summary) {
      latestProposedOutline.value = {
        title: res.proposed_outline.title,
        summary: res.proposed_outline.summary,
      }
    }
    latestUpdates.value = {
      new_characters: res.new_characters || [],
      new_locations: res.new_locations || [],
      new_factions: res.new_factions || [],
      foreshadowing_plants: res.foreshadowing_plants || [],
      foreshadowing_payoffs: res.foreshadowing_payoffs || [],
    }
    await scrollToBottom()
  } catch (error) {
    globalAlert.showError(`发送失败: ${error instanceof Error ? error.message : '未知错误'}`, '发送失败')
  } finally {
    isSending.value = false
  }
}

const applyProposedOutline = async () => {
  if (!props.chapter || !latestProposedOutline.value || isApplying.value) return

  isApplying.value = true
  try {
    const latestAssistantMessage = messages.value
      .filter(msg => msg.role === 'assistant')
      .map(msg => msg.content)
      .slice(-1)[0]

    const updatedProject = await NovelAPI.applyChapterOutlineConverse(props.projectId, {
      chapter_number: props.chapter.chapter_number,
      title: latestProposedOutline.value.title,
      summary: latestProposedOutline.value.summary,
      ai_message: latestAssistantMessage || undefined,
      new_characters: latestUpdates.value.new_characters,
      new_locations: latestUpdates.value.new_locations,
      new_factions: latestUpdates.value.new_factions,
      foreshadowing_plants: latestUpdates.value.foreshadowing_plants,
      foreshadowing_payoffs: latestUpdates.value.foreshadowing_payoffs,
    })

    const updatedOutline = updatedProject.blueprint?.chapter_outline?.find(
      item => item.chapter_number === props.chapter?.chapter_number
    )
    if (!updatedOutline) {
      throw new Error('未找到更新后的章节大纲')
    }

    emit('saved', updatedOutline)
    globalAlert.showSuccess('章节大纲及相关信息已更新', '保存成功')
    handleClose()
  } catch (error) {
    globalAlert.showError(`保存失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
  } finally {
    isApplying.value = false
  }
}

watch(
  () => [props.show, props.chapter?.chapter_number] as const,
  async ([show]) => {
    if (show) {
      resetSession()
      await loadContext()
    }
  }
)

const handleClose = () => {
  resetSession()
  emit('close')
}
</script>
