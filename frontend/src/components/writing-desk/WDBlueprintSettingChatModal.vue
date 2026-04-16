<template>
  <transition
    enter-active-class="transition-opacity duration-200"
    leave-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div v-if="show" class="md-dialog-overlay" @click.self="$emit('close')">
      <transition
        enter-active-class="transition-all duration-300"
        leave-active-class="transition-all duration-200"
        enter-from-class="opacity-0 scale-95"
        leave-to-class="opacity-0 scale-95"
      >
        <div class="md-dialog blueprint-setting-dialog w-full mx-4 flex flex-col overflow-hidden">
          <div class="p-4 border-b border-gray-200 bg-white">
            <div class="flex justify-between items-center gap-4">
              <div class="flex items-center gap-2">
                <span class="relative flex h-3 w-3">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
                </span>
                <span class="text-sm font-medium text-indigo-600">与“文思”对话中...</span>
              </div>
              <div class="flex items-center gap-4">
                <span v-if="assistantTurnCount > 0" class="text-sm font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-md">
                  第{{ assistantTurnCount }}轮
                </span>
                <button
                  @click="$emit('close')"
                  class="text-gray-400 hover:text-gray-600 transition-colors"
                  aria-label="关闭"
                >
                  <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <p class="text-sm text-gray-500 mt-3">
              这里复用“文思对话”的交互风格。历史对话会展示出来，但后续补设定只会基于当前蓝图和新补充内容给出建议。
            </p>
          </div>

          <div ref="messageContainer" class="flex-1 p-6 overflow-y-auto space-y-6 relative bg-white">
            <transition name="fade">
              <InspirationLoading v-if="isHistoryLoading && messages.length === 0" />
            </transition>

            <div v-if="!isHistoryLoading && messages.length === 0" class="text-center py-16 text-sm text-gray-500">
              还没有补设定对话，直接告诉文思你想补充什么设定，或者先点下面的快捷分类。
            </div>

            <div v-for="(item, index) in messages" :key="item.id ?? `${item.role}-${index}`" class="space-y-3">
              <div
                v-if="shouldShowPhaseTag(index)"
                class="flex justify-center"
              >
                <span class="px-3 py-1 rounded-full bg-gray-100 text-xs text-gray-500">
                  {{ item.phase === 'concept' ? '蓝图生成前的历史对话' : '蓝图后的补设定对话' }}
                </span>
              </div>

              <ChatBubble
                :message="item.message"
                :type="item.role === 'user' ? 'user' : 'ai'"
              />

              <div
                v-if="item.role === 'assistant' && (item.proposed_patch || item.impact_analysis)"
                class="max-w-md lg:max-w-lg ml-0"
              >
                <div class="rounded-2xl border border-gray-200 bg-gray-50 p-4 shadow-sm">
                  <div v-if="item.impact_analysis" class="space-y-2 text-sm text-gray-600">
                    <div class="font-semibold text-gray-800">影响分析</div>
                    <div v-if="item.impact_analysis.summary">
                      {{ item.impact_analysis.summary }}
                    </div>
                    <div v-if="item.impact_analysis.impact_level">
                      风险等级：{{ item.impact_analysis.impact_level }}
                    </div>
                    <div v-if="(item.impact_analysis.impacted_sections || []).length">
                      影响模块：{{ item.impact_analysis.impacted_sections?.join('、') }}
                    </div>
                    <div v-if="(item.impact_analysis.impacted_chapters || []).length">
                      影响章节：{{ item.impact_analysis.impacted_chapters?.join('、') }}
                    </div>
                    <div v-if="(item.impact_analysis.recommended_actions || []).length">
                      建议动作：{{ item.impact_analysis.recommended_actions?.join('；') }}
                    </div>
                  </div>

                  <details
                    v-if="item.proposed_patch"
                    class="mt-3 text-xs text-gray-600"
                  >
                    <summary class="cursor-pointer font-medium">查看建议 patch</summary>
                    <pre class="mt-2 p-3 rounded-xl overflow-x-auto bg-white border border-gray-200">{{ formatPatch(item.proposed_patch) }}</pre>
                  </details>

                  <div class="mt-4 flex justify-end">
                    <button
                      v-if="item.proposed_patch"
                      @click="applyPatch(item)"
                      :disabled="applyingMessageId === (item.id ?? -1) || item.applied_to_blueprint"
                      class="bg-indigo-500 text-white font-medium py-2 px-4 rounded-full hover:bg-indigo-600 transition-all shadow-md disabled:bg-gray-300 disabled:cursor-not-allowed"
                    >
                      {{
                        applyingMessageId === (item.id ?? -1)
                          ? '应用中...'
                          : item.applied_to_blueprint
                            ? '已应用到蓝图'
                            : '应用到蓝图'
                      }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="p-4 border-t border-gray-200 bg-gray-50">
            <ConversationInput
              :ui-control="settingUiControl"
              :loading="isHistoryLoading || isSending"
              @submit="handleUserInput"
            />
          </div>
        </div>
      </transition>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { NovelAPI } from '@/api/novel'
import type {
  BlueprintSettingApplyResponse,
  BlueprintSettingChatMessage,
  BlueprintSettingConverseResponse,
  BlueprintSettingHistoryResponse,
  NovelProject,
  UIControl,
} from '@/api/novel'
import ChatBubble from '@/components/ChatBubble.vue'
import ConversationInput from '@/components/ConversationInput.vue'
import InspirationLoading from '@/components/InspirationLoading.vue'
import { globalAlert } from '@/composables/useAlert'

interface Props {
  show: boolean
  projectId: string
}

type ConversationSubmit = { id: string; value: string } | null

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  applied: [project: NovelProject]
}>()

const messages = ref<BlueprintSettingChatMessage[]>([])
const isHistoryLoading = ref(false)
const isSending = ref(false)
const applyingMessageId = ref<number | null>(null)
const historyLoaded = ref(false)
const messageContainer = ref<HTMLElement | null>(null)

const settingUiControl = ref<UIControl>({
  type: 'single_choice',
  options: [
    { id: 'role_setting', label: '角色设定（配角、女主、敌人）' },
    { id: 'goldfinger_setting', label: '外挂系统细节（规则、代价、封象）' },
    { id: 'sect_setting', label: '宗门设定（派系、资源、关系）' },
    { id: 'battle_setting', label: '战役设定（外敌身份、关键战役）' },
    { id: 'emotion_setting', label: '感情线设定（候选人、推进节奏）' },
    { id: 'world_expansion', label: '世界观扩展（外敌来源、势力格局）' },
    { id: 'cultivation_setting', label: '功法/法宝设定' },
    { id: 'other', label: '其他（告诉我们想加什么）' },
  ],
  placeholder: '选择上方选项或点击“我要输入”',
})

const assistantTurnCount = computed(() => {
  return messages.value.filter(item => item.role === 'assistant').length
})

const normalizeMessage = (raw: any): BlueprintSettingChatMessage | null => {
  if (!raw || typeof raw !== 'object') return null
  const role = raw.role === 'user' ? 'user' : 'assistant'
  const message = String(raw.message ?? raw.ai_message ?? raw.content ?? '').trim()
  if (!message) return null
  return {
    id: typeof raw.id === 'number' ? raw.id : undefined,
    role,
    message,
    phase: typeof raw.phase === 'string' ? raw.phase : undefined,
    created_at: raw.created_at,
    proposed_patch: raw.proposed_patch ?? null,
    impact_analysis: raw.impact_analysis ?? null,
    applied_to_blueprint: Boolean(raw.applied_to_blueprint),
    source: typeof raw.source === 'string' ? raw.source : undefined,
    metadata: raw.metadata ?? null,
  }
}

const shouldShowPhaseTag = (index: number) => {
  if (index === 0) return true
  return messages.value[index - 1]?.phase !== messages.value[index]?.phase
}

const formatPatch = (patch: Record<string, any>) => JSON.stringify(patch, null, 2)

const scrollToBottom = async () => {
  await nextTick()
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

const buildMessageFromInput = (userInput: ConversationSubmit): string => {
  if (!userInput) return ''
  if (userInput.id === 'text_input') {
    return userInput.value.trim()
  }

  const promptMap: Record<string, string> = {
    role_setting: '我想补充角色设定，请围绕配角、女主、敌人等方向帮我细化，并给出可以应用到蓝图的建议。',
    goldfinger_setting: '我想补充外挂系统细节，请聚焦规则、代价、限制和表现形式，帮我细化并给出可以应用到蓝图的建议。',
    sect_setting: '我想补充宗门设定，请围绕派系、资源、内部关系和外部竞争帮我细化，并给出可以应用到蓝图的建议。',
    battle_setting: '我想补充战役设定，请围绕外敌身份、冲突原因、关键战役和后果帮我细化，并给出可以应用到蓝图的建议。',
    emotion_setting: '我想补充感情线设定，请围绕候选人、关系变化和推进节奏帮我细化，并给出可以应用到蓝图的建议。',
    world_expansion: '我想扩展世界观，请围绕外敌来源、势力格局和更大的世界背景帮我细化，并给出可以应用到蓝图的建议。',
    cultivation_setting: '我想补充功法或法宝设定，请围绕体系、能力、限制和成长路径帮我细化，并给出可以应用到蓝图的建议。',
    other: '我还想补充一些其他设定，请你先帮我梳理还能从哪些方向继续细化。',
  }

  return promptMap[userInput.id] || userInput.value.trim()
}

const loadHistory = async () => {
  if (!props.projectId) return
  isHistoryLoading.value = true
  try {
    const res = await NovelAPI.getBlueprintSettingChatHistory(props.projectId) as BlueprintSettingHistoryResponse | any
    const rawMessages = Array.isArray(res) ? res : (res?.messages || res?.history || [])
    messages.value = rawMessages
      .map((item: any) => normalizeMessage(item))
      .filter((item: BlueprintSettingChatMessage | null): item is BlueprintSettingChatMessage => item !== null)
    historyLoaded.value = true
    await scrollToBottom()
  } catch (error) {
    globalAlert.showError(`加载历史失败: ${error instanceof Error ? error.message : '未知错误'}`, '加载失败')
  } finally {
    isHistoryLoading.value = false
  }
}

const sendMessage = async (text: string) => {
  if (!text || !props.projectId || isSending.value) return

  isSending.value = true
  messages.value.push({
    role: 'user',
    message: text,
    phase: 'post_blueprint_setting',
    source: 'blueprint_setting',
  })
  await scrollToBottom()

  try {
    const res = await NovelAPI.converseBlueprintSettingChat(props.projectId, text) as BlueprintSettingConverseResponse | any
    const rawMessages = Array.isArray(res?.history)
      ? res.history
      : (Array.isArray(res?.messages) ? res.messages : null)

    if (rawMessages) {
      messages.value = rawMessages
        .map((item: any) => normalizeMessage(item))
        .filter((item: BlueprintSettingChatMessage | null): item is BlueprintSettingChatMessage => item !== null)
    } else {
      const fallbackAssistant = normalizeMessage({
        role: 'assistant',
        message: res?.ai_message ?? '',
        proposed_patch: res?.proposed_patch ?? null,
        impact_analysis: res?.impact_analysis ?? null,
        phase: 'post_blueprint_setting',
        source: 'blueprint_setting',
      })
      if (fallbackAssistant) {
        messages.value.push(fallbackAssistant)
      }
    }

    await scrollToBottom()
  } catch (error) {
    if (messages.value.length > 0) {
      const lastMessage = messages.value[messages.value.length - 1]
      if (lastMessage.role === 'user' && lastMessage.message === text && !lastMessage.id) {
        messages.value.pop()
      }
    }
    globalAlert.showError(`发送失败: ${error instanceof Error ? error.message : '未知错误'}`, '发送失败')
  } finally {
    isSending.value = false
  }
}

const handleUserInput = async (userInput: ConversationSubmit) => {
  const message = buildMessageFromInput(userInput)
  if (!message) return
  await sendMessage(message)
}

const resolveProjectFromApplyResponse = (res: BlueprintSettingApplyResponse | NovelProject | any): NovelProject | null => {
  if (res && typeof res === 'object') {
    if (typeof res.id === 'string' && res.blueprint) return res as NovelProject
    if (res.project && typeof res.project.id === 'string') return res.project as NovelProject
    if (res.data?.project && typeof res.data.project.id === 'string') return res.data.project as NovelProject
  }
  return null
}

const applyPatch = async (item: BlueprintSettingChatMessage) => {
  if (!props.projectId || !item.proposed_patch) return
  const itemId = item.id ?? -1
  if (applyingMessageId.value === itemId || item.applied_to_blueprint) return

  applyingMessageId.value = itemId
  try {
    const res = await NovelAPI.applyBlueprintSettingPatch(props.projectId, item.proposed_patch, item.id ?? null)
    const updatedProject = resolveProjectFromApplyResponse(res)
    if (updatedProject) {
      emit('applied', updatedProject)
      item.applied_to_blueprint = true
      globalAlert.showSuccess('蓝图已更新', '应用成功')
    } else {
      globalAlert.showError('后端返回中未找到最新项目数据', '应用失败')
    }
  } catch (error) {
    globalAlert.showError(`应用失败: ${error instanceof Error ? error.message : '未知错误'}`, '应用失败')
  } finally {
    applyingMessageId.value = null
  }
}

watch(
  () => props.projectId,
  () => {
    historyLoaded.value = false
    messages.value = []
  }
)

watch(
  () => props.show,
  async visible => {
    if (visible && !historyLoaded.value) {
      await loadHistory()
    }
    if (visible) {
      await scrollToBottom()
    }
  }
)
</script>

<style scoped>
:deep(.blueprint-setting-dialog) {
  width: min(94vw, 1360px) !important;
  max-width: min(94vw, 1360px) !important;
  height: min(92vh, 1080px);
  max-height: 92vh !important;
}

:deep(.chat-bubble-ai) {
  max-width: min(860px, calc(100% - 28px)) !important;
  padding: 16px 18px !important;
}

:deep(.chat-bubble-ai .prose) {
  font-size: 15px;
  line-height: 1.9;
  letter-spacing: 0.01em;
}

:deep(.chat-bubble-ai .prose p) {
  margin-top: 0.55em;
  margin-bottom: 0.55em;
}

:deep(.chat-bubble-ai .prose li) {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
}

@media (max-width: 768px) {
  :deep(.blueprint-setting-dialog) {
    width: calc(100vw - 16px) !important;
    max-width: calc(100vw - 16px) !important;
    height: 94vh;
    max-height: 94vh !important;
  }

  :deep(.chat-bubble-ai) {
    max-width: calc(100% - 12px) !important;
    padding: 14px 14px !important;
  }

  :deep(.chat-bubble-ai .prose) {
    font-size: 14px;
    line-height: 1.8;
  }
}
</style>
