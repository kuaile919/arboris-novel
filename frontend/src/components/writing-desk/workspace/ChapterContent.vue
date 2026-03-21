<!-- AIMETA P=章节内容_章节文本展示编辑|R=内容展示_编辑|NR=不含版本管理|E=component:ChapterContent|X=internal|A=内容组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-6">
    <div class="md-card md-card-filled p-4 mb-6" style="border-radius: var(--md-radius-lg); background-color: var(--md-success-container);">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2" style="color: var(--md-on-success-container);">
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
          </svg>
          <span class="font-medium">这个章节已经完成</span>
        </div>

        <button
          v-if="selectedChapter.versions && selectedChapter.versions.length > 0"
          @click="$emit('showVersionSelector', true)"
          class="md-btn md-btn-text md-ripple flex items-center gap-1"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"></path>
            <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"></path>
          </svg>
          查看所有版本
        </button>
      </div>
    </div>

    <div class="md-card md-card-outlined p-6" style="border-radius: var(--md-radius-xl);">
      <div class="flex items-center justify-between mb-4 gap-3">
        <h4 class="md-title-medium font-semibold">章节内容</h4>
        <div class="flex items-center gap-3">
          <div class="md-body-small md-on-surface-variant">
            约 {{ Math.round(cleanVersionContent(selectedChapter.content || '').length / 100) * 100 }} 字
          </div>
          <!-- 分层优化按钮 -->
          <button
            class="md-btn md-btn-tonal md-ripple flex items-center gap-1"
            @click="showOptimizer = true"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
            </svg>
            分层优化
          </button>
          <button
            class="md-btn md-btn-outlined md-ripple flex items-center gap-1"
            @click="viewLatestOptimizeResult"
            :disabled="isCheckingOptimizeResult"
            :class="{ 'opacity-70': isCheckingOptimizeResult }"
          >
            <svg v-if="isCheckingOptimizeResult" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h14a2 2 0 012 2v4M3 19a2 2 0 002 2h14a2 2 0 002-2v-4M7 10h10m-10 4h10" />
            </svg>
            {{ isCheckingOptimizeResult ? '查看中...' : '查看优化结果' }}
          </button>
          <!-- 查看摘要按钮 -->
          <button
            class="md-btn md-btn-outlined md-ripple flex items-center gap-1"
            @click="viewSummary"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            查看摘要
          </button>
          <!-- 立即摘要按钮 -->
          <button
            class="md-btn md-btn-filled md-ripple flex items-center gap-1 transition-all"
            @click="generateSummary"
            :disabled="isGeneratingSummary"
            :class="{ 'opacity-70': isGeneratingSummary }"
          >
            <svg v-if="isGeneratingSummary" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
            </svg>
            <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            {{ isGeneratingSummary ? '提交中...' : '立即摘要' }}
          </button>
          <button
            class="md-btn md-btn-outlined md-ripple flex items-center gap-1"
            :class="selectedChapter.content ? '' : 'opacity-50 cursor-not-allowed'"
            :disabled="!selectedChapter.content"
            @click="exportChapterAsTxt(selectedChapter)"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v16h16V4m-4 4l-4-4-4 4m4-4v12" />
            </svg>
            导出TXT
          </button>
        </div>
      </div>
      <div class="prose max-w-none">
        <div class="whitespace-pre-wrap leading-relaxed" style="color: var(--md-on-surface);">{{ cleanVersionContent(selectedChapter.content || '') }}</div>
      </div>
    </div>

    <!-- 分层优化弹窗 -->
    <Teleport to="body">
      <div
        v-if="showOptimizer"
        class="md-dialog-overlay"
        @click.self="showOptimizer = false"
      >
        <div class="md-dialog m3-optimizer-dialog">
          <div class="p-6">
            <!-- 优化面板头部 -->
            <div class="flex items-center justify-between mb-6">
              <div>
                <h3 class="md-headline-small font-semibold">✨ 分层优化</h3>
                <p class="md-body-small md-on-surface-variant mt-1">选择一个维度进行深度优化，让文字更有灵魂</p>
              </div>
              <button
                @click="showOptimizer = false"
                class="md-icon-btn md-ripple"
              >
                <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                </svg>
              </button>
            </div>

            <!-- 优化维度选择 -->
            <div class="grid grid-cols-2 gap-4 mb-6">
              <button
                v-for="dim in optimizeDimensions"
                :key="dim.key"
                @click="selectedDimension = dim.key"
                :class="[
                  'md-card md-card-outlined p-4 text-left transition-all duration-200',
                  selectedDimension === dim.key
                    ? 'm3-option-selected'
                    : 'm3-option'
                ]"
              >
                <div class="flex items-center gap-3 mb-2">
                  <span class="text-2xl">{{ dim.icon }}</span>
                  <span class="md-title-small font-semibold">{{ dim.label }}</span>
                </div>
                <p class="md-body-small md-on-surface-variant">{{ dim.description }}</p>
              </button>
            </div>

            <!-- 额外说明 -->
            <div class="mb-6">
              <label class="md-text-field-label mb-2">
                额外优化指令（可选）
              </label>
              <textarea
                v-model="additionalNotes"
                rows="3"
                class="md-textarea w-full resize-none"
                placeholder="例如：加强主角内心的挣扎感，让对话更有张力..."
              ></textarea>
            </div>

            <!-- 操作按钮 -->
            <div class="flex justify-end gap-3">
              <button
                @click="showOptimizer = false"
                class="md-btn md-btn-outlined md-ripple"
              >
                取消
              </button>
              <button
                @click="startOptimize"
                :disabled="!selectedDimension || isOptimizing"
                class="md-btn md-btn-filled md-ripple disabled:opacity-50 flex items-center gap-2"
              >
                <svg v-if="isOptimizing" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
                </svg>
                {{ isOptimizing ? '优化中...' : '开始优化' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 优化结果对比弹窗 -->
    <Teleport to="body">
      <div
        v-if="showOptimizeResult"
        class="md-dialog-overlay"
        @click.self="showOptimizeResult = false"
      >
        <div class="md-dialog m3-result-dialog flex flex-col">
          <div class="p-6 border-b" style="border-bottom-color: var(--md-outline-variant);">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="md-headline-small font-semibold">✨ 优化结果对比</h3>
                <p class="md-body-small md-on-surface-variant mt-1">{{ optimizeResultNotes }}</p>
              </div>
              <button
                @click="showOptimizeResult = false"
                class="md-icon-btn md-ripple"
              >
                <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                </svg>
              </button>
            </div>
          </div>
          <div class="flex-1 overflow-y-auto p-6">
            <!-- 文本对比视图 -->
            <TextDiffViewer
              :original-text="originalContent"
              :optimized-text="optimizedContent"
              :editable-optimized="true"
              @update:optimized-text="optimizedContent = $event"
            />
          </div>
          <div class="p-6 border-t flex justify-between gap-3" style="border-top-color: var(--md-outline-variant);">
            <button
              @click="saveToStyleLibrary"
              :disabled="isSavingStyle"
              class="md-btn md-btn-tonal md-ripple disabled:opacity-50 flex items-center gap-2"
            >
              <svg v-if="isSavingStyle" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
              </svg>
              <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
              </svg>
              {{ isSavingStyle ? '保存中...' : '保存到风格库' }}
            </button>
            <div class="flex gap-3">
              <button
                @click="showOptimizeResult = false"
                class="md-btn md-btn-outlined md-ripple"
              >
                取消
              </button>
              <button
                @click="applyOptimization"
                :disabled="isApplying"
                class="md-btn md-btn-filled md-ripple disabled:opacity-50 flex items-center gap-2"
                style="background-color: var(--md-success); color: var(--md-on-success);"
              >
                <svg v-if="isApplying" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
                </svg>
                {{ isApplying ? '应用中...' : '应用优化' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 查看摘要弹窗 -->
    <Teleport to="body">
      <div
        v-if="showSummaryDialog"
        class="md-dialog-overlay"
        @click.self="closeSummaryDialog"
      >
        <div class="md-dialog m3-summary-dialog">
          <div class="p-6">
            <div class="flex items-center justify-between mb-4">
              <h3 class="md-headline-small font-semibold">📝 章节摘要</h3>
              <div class="flex items-center gap-2">
                <!-- 编辑按钮 -->
                <button
                  v-if="chapterSummary && !isEditingSummary && !isLoadingSummary"
                  @click="startEditSummary"
                  class="md-icon-btn md-ripple"
                  title="编辑"
                >
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <!-- 关闭按钮 -->
                <button
                  @click="closeSummaryDialog"
                  class="md-icon-btn md-ripple"
                >
                  <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                  </svg>
                </button>
              </div>
            </div>

            <div v-if="isLoadingSummary" class="flex items-center justify-center py-12">
              <div class="text-center">
                <svg class="w-12 h-12 animate-spin mx-auto mb-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
                </svg>
                <p class="text-gray-600">加载中...</p>
              </div>
            </div>

            <div v-else-if="!chapterSummary" class="py-12 text-center">
              <svg class="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p class="text-gray-600 mb-4">该章节暂无摘要</p>
              <button
                @click="generateSummaryFromDialog"
                class="md-btn md-btn-filled md-ripple"
              >
                立即生成摘要
              </button>
            </div>

            <!-- 有摘要内容时 -->
            <div v-else class="summary-wrapper">
              <!-- 内容区域 - 使用相同的样式类 -->
              <div class="summary-content-box">
                <!-- 编辑模式 -->
                <textarea
                  v-if="isEditingSummary"
                  v-model="editedSummary"
                  class="summary-textarea"
                  placeholder="请输入章节摘要..."
                ></textarea>
                <!-- 查看模式 -->
                <div v-else class="summary-view">
                  <p class="text-sm leading-relaxed whitespace-pre-wrap" style="color: var(--md-on-surface);">{{ chapterSummary }}</p>
                </div>
              </div>

              <!-- 底部操作区域 -->
              <div class="summary-footer">
                <!-- 编辑模式按钮 -->
                <template v-if="isEditingSummary">
                  <button
                    @click="cancelEditSummary"
                    class="md-btn md-btn-outlined md-ripple"
                  >
                    取消
                  </button>
                  <button
                    @click="saveSummary"
                    :disabled="isSavingSummary || !editedSummary.trim()"
                    class="md-btn md-btn-filled md-ripple disabled:opacity-50 flex items-center gap-2"
                  >
                    <svg v-if="isSavingSummary" class="w-4 h-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
                    </svg>
                    {{ isSavingSummary ? '保存中...' : '保存' }}
                  </button>
                </template>
                <!-- 查看模式 - 提示信息 -->
                <template v-else>
                  <span class="text-sm text-gray-400">点击右上角编辑按钮修改摘要</span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import type { Chapter } from '@/api/novel'
import { OptimizerAPI } from '@/api/novel'
import TextDiffViewer from '@/components/TextDiffViewer.vue'

interface Props {
  selectedChapter: Chapter
  projectId?: string
}

const props = defineProps<Props>()

defineEmits(['showVersionSelector'])

// 优化相关状态
const showOptimizer = ref(false)
const showOptimizeResult = ref(false)
const selectedDimension = ref<string>('')
const additionalNotes = ref('')
const isOptimizing = ref(false)
const isApplying = ref(false)
const isSavingStyle = ref(false)
const originalContent = ref('')
const optimizedContent = ref('')
const optimizeResultNotes = ref('')
const optimizeTaskId = ref<string | null>(null)
const isCheckingOptimizeResult = ref(false)
let optimizePollingTimer: ReturnType<typeof setInterval> | null = null

// 摘要相关状态
const showSummaryDialog = ref(false)
const isLoadingSummary = ref(false)
const isGeneratingSummary = ref(false)
const isSavingSummary = ref(false)
const isEditingSummary = ref(false)
const chapterSummary = ref<string | null>(null)
const editedSummary = ref<string>('')

// 优化维度配置
const optimizeDimensions = [
  {
    key: 'dialogue',
    icon: '💬',
    label: '对话优化',
    description: '让每句对话都有独特的声音和潜台词'
  },
  {
    key: 'environment',
    icon: '🌄',
    label: '环境描写',
    description: '让场景氛围与情绪完美融合'
  },
  {
    key: 'psychology',
    icon: '🧠',
    label: '心理活动',
    description: '深入角色内心，展现复杂情感'
  },
  {
    key: 'logic',
    icon: '🔗',
    label: '逻辑优化',
    description: '优化情节逻辑，消除前后矛盾'
  },
  {
    key: 'rhythm',
    icon: '🎵',
    label: '节奏韵律',
    description: '优化文字节奏，增强阅读体验'
  }
]

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

const sanitizeFileName = (name: string): string => {
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

const exportChapterAsTxt = (chapter?: Chapter | null) => {
  if (!chapter) return

  const title = chapter.title?.trim() || `第${chapter.chapter_number}章`
  const safeTitle = sanitizeFileName(title) || `chapter-${chapter.chapter_number}`
  const content = cleanVersionContent(chapter.content || '')
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${safeTitle}.txt`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const stopOptimizePolling = () => {
  if (optimizePollingTimer) {
    clearInterval(optimizePollingTimer)
    optimizePollingTimer = null
  }
}

const openOptimizeResultFromTask = (task: {
  dimension: string
  original_content?: string | null
  optimized_content?: string | null
  optimization_notes?: string | null
}) => {
  selectedDimension.value = task.dimension
  originalContent.value = task.original_content || cleanVersionContent(props.selectedChapter.content || '')
  optimizedContent.value = task.optimized_content || ''
  optimizeResultNotes.value = task.optimization_notes || '优化完成'
  showOptimizeResult.value = true
}

const startOptimizePolling = (taskId: string) => {
  stopOptimizePolling()
  optimizePollingTimer = setInterval(async () => {
    try {
      const task = await OptimizerAPI.getOptimizeTaskStatus(taskId)
      if (task.status === 'completed') {
        openOptimizeResultFromTask(task)
        stopOptimizePolling()
      } else if (task.status === 'failed') {
        globalAlert.showError(task.error_message || '优化任务失败')
        stopOptimizePolling()
      }
    } catch {
      // 轮询异常时静默，避免打断用户
    }
  }, 5000)
}

const startOptimize = async () => {
  if (!selectedDimension.value || !props.projectId) {
    globalAlert.showError('请选择优化维度')
    return
  }

  isOptimizing.value = true
  showOptimizer.value = false

  // 保存原始内容
  originalContent.value = cleanVersionContent(props.selectedChapter.content || '')

  try {
    const task = await OptimizerAPI.optimizeChapterAsync({
      project_id: props.projectId,
      chapter_number: props.selectedChapter.chapter_number,
      dimension: selectedDimension.value as 'dialogue' | 'environment' | 'psychology' | 'logic' | 'rhythm',
      additional_notes: additionalNotes.value || undefined
    })
    optimizeTaskId.value = task.task_id
    startOptimizePolling(task.task_id)
    globalAlert.showSuccess('优化任务已启动。你可以切换页面，稍后点“查看优化结果”')
  } catch (error: any) {
    console.error('优化失败:', error)
    globalAlert.showError(error.message || '优化失败，请稍后重试')
  } finally {
    isOptimizing.value = false
  }
}

const viewLatestOptimizeResult = async () => {
  if (!props.projectId) return

  isCheckingOptimizeResult.value = true
  try {
    const task = await OptimizerAPI.getLatestOptimizationResult(
      props.projectId,
      props.selectedChapter.chapter_number
    )
    optimizeTaskId.value = task.task_id

    if (task.status === 'completed') {
      openOptimizeResultFromTask(task)
      return
    }

    if (task.status === 'failed') {
      globalAlert.showError(task.error_message || '最近一次优化任务失败')
      return
    }

    startOptimizePolling(task.task_id)
    globalAlert.showSuccess('优化仍在进行中，请稍后再查看')
  } catch (error: any) {
    console.error('鑾峰彇浼樺寲缁撴灉澶辫触:', error)
    globalAlert.showError(error.message || '暂无可查看的优化结果')
  } finally {
    isCheckingOptimizeResult.value = false
  }
}

const applyOptimization = async () => {
  if (!optimizedContent.value || !props.projectId) return

  isApplying.value = true

  try {
    await OptimizerAPI.applyOptimization(
      props.projectId,
      props.selectedChapter.chapter_number,
      optimizedContent.value
    )

    globalAlert.showSuccess('优化内容已应用')
    showOptimizeResult.value = false

    // 重置状态
    selectedDimension.value = ''
    additionalNotes.value = ''
    originalContent.value = ''
    optimizedContent.value = ''
    optimizeResultNotes.value = ''
    optimizeTaskId.value = null
    stopOptimizePolling()

    // 刷新页面以显示新内容
    window.location.reload()
  } catch (error: any) {
    console.error('应用优化失败:', error)
    globalAlert.showError(error.message || '应用优化失败，请稍后重试')
  } finally {
    isApplying.value = false
  }
}

// 保存到风格库
const saveToStyleLibrary = async () => {
  if (!selectedDimension.value || !optimizeResultNotes.value) {
    globalAlert.showError('缺少必要信息，无法保存')
    return
  }

  isSavingStyle.value = true

  try {
    const result = await OptimizerAPI.appendWritingStyle(
      selectedDimension.value,
      additionalNotes.value || '',
      optimizeResultNotes.value
    )

    globalAlert.showSuccess(`已将优化经验保存到写作风格库`)
    console.log('提炼的写作原则:', result.summary)
  } catch (error: any) {
    console.error('保存到风格库失败:', error)
    globalAlert.showError(error.message || '保存失败，请稍后重试')
  } finally {
    isSavingStyle.value = false
  }
}

const viewSummary = async () => {
  if (!props.projectId) return

  showSummaryDialog.value = true
  isLoadingSummary.value = true
  isEditingSummary.value = false

  try {
    const result = await OptimizerAPI.getChapterSummary(
      props.projectId,
      props.selectedChapter.chapter_number
    )

    chapterSummary.value = result.summary
  } catch (error: any) {
    console.error('获取摘要失败:', error)
    globalAlert.showError(error.message || '获取摘要失败')
  } finally {
    isLoadingSummary.value = false
  }
}

const startEditSummary = () => {
  isEditingSummary.value = true
  editedSummary.value = chapterSummary.value || ''
}

const cancelEditSummary = () => {
  isEditingSummary.value = false
  editedSummary.value = ''
}

const closeSummaryDialog = () => {
  if (isEditingSummary.value) {
    if (confirm('有未保存的修改，确定要关闭吗？')) {
      showSummaryDialog.value = false
      isEditingSummary.value = false
      editedSummary.value = ''
    }
  } else {
    showSummaryDialog.value = false
  }
}

const saveSummary = async () => {
  if (!props.projectId || !editedSummary.value.trim()) return

  isSavingSummary.value = true

  try {
    await OptimizerAPI.updateChapterSummary(
      props.projectId,
      props.selectedChapter.chapter_number,
      editedSummary.value.trim()
    )

    chapterSummary.value = editedSummary.value.trim()
    isEditingSummary.value = false
    editedSummary.value = ''
    globalAlert.showSuccess('摘要已保存')
  } catch (error: any) {
    console.error('保存摘要失败:', error)
    globalAlert.showError(error.message || '保存摘要失败')
  } finally {
    isSavingSummary.value = false
  }
}

const generateSummary = async () => {
  if (!props.projectId) return

  isGeneratingSummary.value = true

  try {
    // 异步调用API，不等待完成
    OptimizerAPI.generateChapterSummary(
      props.projectId,
      props.selectedChapter.chapter_number
    ).then(() => {
      // 成功后可以选择性地刷新摘要
      console.log('摘要生成完成')
    }).catch((error) => {
      console.error('摘要生成失败:', error)
    })

    // 立即显示提示并重置状态，让用户可以继续操作
    globalAlert.showSuccess('摘要生成任务已启动，请稍后查看摘要内容')
  } catch (error: any) {
    console.error('启动摘要生成失败:', error)
    globalAlert.showError(error.message || '启动摘要生成失败')
  } finally {
    // 短暂延迟后重置状态，显示加载动画
    setTimeout(() => {
      isGeneratingSummary.value = false
    }, 800)
  }
}

const generateSummaryFromDialog = async () => {
  showSummaryDialog.value = false
  await generateSummary()
}

onBeforeUnmount(() => {
  stopOptimizePolling()
})
</script>

<style scoped>
.m3-optimizer-dialog {
  max-width: min(720px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}

.m3-result-dialog {
  max-width: min(1200px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}

.m3-summary-dialog {
  max-width: min(600px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}

.m3-option {
  border-color: var(--md-outline-variant);
}

.m3-option-selected {
  border-color: var(--md-primary);
  background-color: var(--md-primary-container);
  box-shadow: var(--md-elevation-1);
}

/* 摘要弹窗 - 固定宽度和高度 */
.m3-summary-dialog {
  width: 600px !important;
  min-width: 600px;
  max-width: 600px;
}

/* 摘要容器 */
.summary-wrapper {
  width: 100%;
  height: 450px;
  display: flex;
  flex-direction: column;
}

/* 摘要内容框 - 编辑和查看共用 */
.summary-content-box {
  flex: 1;
  width: 100%;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--md-outline-variant);
  background-color: #f9fafb;
  margin-bottom: 16px;
}

/* 编辑模式文本框 */
.summary-textarea {
  width: 100%;
  height: 100%;
  padding: 16px;
  border: none;
  background-color: transparent;
  resize: none;
  outline: none;
  font-size: 14px;
  line-height: 1.6;
}

/* 查看模式 */
.summary-view {
  width: 100%;
  height: 100%;
  padding: 16px;
  overflow-y: auto;
}

/* 底部操作区域 */
.summary-footer {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
</style>
