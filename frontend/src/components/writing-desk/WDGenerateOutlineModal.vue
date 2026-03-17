<!-- AIMETA P=生成大纲弹窗_大纲生成界面|R=大纲生成表单|NR=不含生成逻辑|E=component:WDGenerateOutlineModal|X=ui|A=生成弹窗|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="handleClose">
      <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0" enter-to="opacity-100" leave="ease-in duration-200" leave-from="opacity-100" leave-to="opacity-0">
        <div class="fixed inset-0" style="background-color: rgba(0, 0, 0, 0.32);" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" enter-to="opacity-100 translate-y-0 sm:scale-100" leave="ease-in duration-200" leave-from="opacity-100 translate-y-0 sm:scale-100" leave-to="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95">
            <DialogPanel :class="['md-dialog m3-outline-dialog text-left transition-all sm:my-6 sm:w-full', isPreviewMode ? 'sm:max-w-4xl' : 'sm:max-w-lg']">
              <!-- 输入模式 -->
              <template v-if="!isPreviewMode">
                <div class="px-5 pt-6 pb-5 sm:px-6 sm:pt-6 sm:pb-5">
                  <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
                    <div class="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full sm:mx-0 sm:h-12 sm:w-12" style="background-color: var(--md-primary-container);">
                      <svg class="h-6 w-6" style="color: var(--md-on-primary-container);" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
                      </svg>
                    </div>
                    <div class="text-center sm:flex-1 sm:text-left">
                      <DialogTitle as="h3" class="md-headline-small font-semibold leading-7">生成后续大纲</DialogTitle>
                      <div class="mt-2">
                        <p class="md-body-medium md-on-surface-variant">请输入或选择要生成的后续章节数量。</p>
                      </div>
                    </div>
                  </div>
                  <div class="mt-6">
                    <label for="numChapters" class="md-text-field-label">生成数量</label>
                    <input type="number" name="numChapters" id="numChapters" v-model.number="numChapters" class="md-text-field-input w-full mt-2" min="1" max="20">
                    <div class="mt-5 flex flex-wrap justify-center gap-3">
                      <button v-for="count in [1, 2, 5, 10]" :key="count" @click="setNumChapters(count)"
                        :class="['md-btn md-btn-outlined md-ripple', numChapters === count ? 'm3-count-selected' : '']">
                        {{ count }} 章
                      </button>
                    </div>
                  </div>
                  <!-- 用户提示文字输入 -->
                  <div class="mt-6">
                    <label for="userHint" class="md-text-field-label">创作提示 <span class="md-on-surface-variant text-sm">(可选)</span></label>
                    <textarea
                      id="userHint"
                      v-model="userHint"
                      class="md-text-field-input w-full mt-2 resize-none"
                      rows="3"
                      placeholder="输入提示文字指导大纲生成方向，例如：主角将遇到新的挑战..."
                    ></textarea>
                  </div>
                </div>
                <div class="px-6 py-4 sm:flex sm:flex-row-reverse sm:px-8" style="background-color: var(--md-surface-container-low);">
                  <button type="button" class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center" @click="handlePreview" :disabled="isLoading">
                    {{ isLoading ? '生成中...' : '生成预览' }}
                  </button>
                  <button type="button" class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3" @click="handleClose">取消</button>
                </div>
              </template>

              <!-- 预览模式 -->
              <template v-else>
                <div class="px-5 pt-6 pb-5 sm:px-6 sm:pt-6 sm:pb-5">
                  <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
                    <div class="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full sm:mx-0 sm:h-12 sm:w-12" style="background-color: var(--md-primary-container);">
                      <svg class="h-6 w-6" style="color: var(--md-on-primary-container);" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div class="text-center sm:flex-1 sm:text-left">
                      <DialogTitle as="h3" class="md-headline-small font-semibold leading-7">大纲预览确认</DialogTitle>
                      <div class="mt-2">
                        <p class="md-body-medium md-on-surface-variant">请查看生成的大纲预览，确认后保存到数据库。</p>
                      </div>
                    </div>
                  </div>

                  <!-- 预览内容 -->
                  <div class="mt-6 max-h-96 overflow-y-auto">
                    <!-- 章节大纲 -->
                    <div v-if="previewData?.chapters?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">章节大纲 ({{ previewData.chapters.length }} 章)</h4>
                      <div class="space-y-3">
                        <div v-for="chapter in previewData.chapters" :key="chapter.chapter_number" class="p-3 rounded-lg" style="background-color: var(--md-surface-container);">
                          <div class="flex items-center gap-2 mb-1">
                            <span class="font-semibold" style="color: var(--md-primary);">第 {{ chapter.chapter_number }} 章</span>
                            <span class="md-body-medium">{{ chapter.title }}</span>
                          </div>
                          <p class="md-body-small md-on-surface-variant">{{ chapter.summary }}</p>
                          <!-- 伏笔详情展示 -->
                          <div v-if="chapter.foreshadowing?.plant?.length || chapter.foreshadowing?.payoff?.length" class="mt-2 space-y-1">
                            <div v-if="chapter.foreshadowing?.plant?.length" class="text-xs">
                              <span class="px-2 py-0.5 rounded" style="background-color: var(--md-tertiary-container); color: var(--md-on-tertiary-container);">
                                埋设:
                              </span>
                              <span class="ml-1 md-on-surface-variant">{{ chapter.foreshadowing.plant.join('；') }}</span>
                            </div>
                            <div v-if="chapter.foreshadowing?.payoff?.length" class="text-xs">
                              <span class="px-2 py-0.5 rounded" style="background-color: var(--md-secondary-container); color: var(--md-on-secondary-container);">
                                回收:
                              </span>
                              <span class="ml-1 md-on-surface-variant">{{ chapter.foreshadowing.payoff.join('；') }}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <!-- 新角色 -->
                    <div v-if="previewData?.new_characters?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">新角色 ({{ previewData.new_characters.length }})</h4>
                      <div class="flex flex-wrap gap-2">
                        <span v-for="char in previewData.new_characters" :key="char.name" class="text-sm px-3 py-1 rounded-full" style="background-color: var(--md-primary-container); color: var(--md-on-primary-container);">
                          {{ char.name }} <span v-if="char.identity">({{ char.identity }})</span>
                        </span>
                      </div>
                    </div>

                    <!-- 新关系 -->
                    <div v-if="previewData?.new_relationships?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">新关系 ({{ previewData.new_relationships.length }})</h4>
                      <div class="space-y-1">
                        <div v-for="(rel, idx) in previewData.new_relationships" :key="idx" class="text-sm">
                          <span style="color: var(--md-primary);">{{ rel.character_from }}</span>
                          <span class="md-on-surface-variant"> → </span>
                          <span style="color: var(--md-primary);">{{ rel.character_to }}</span>
                          <span class="md-on-surface-variant">: {{ rel.description }}</span>
                        </div>
                      </div>
                    </div>

                    <!-- 新地点 -->
                    <div v-if="previewData?.new_locations?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">新地点 ({{ previewData.new_locations.length }})</h4>
                      <div class="flex flex-wrap gap-2">
                        <span v-for="loc in previewData.new_locations" :key="loc.name" class="text-sm px-3 py-1 rounded-full" style="background-color: var(--md-surface-container-high);">
                          {{ loc.name }} <span v-if="loc.type">({{ loc.type }})</span>
                        </span>
                      </div>
                    </div>

                    <!-- 新势力 -->
                    <div v-if="previewData?.new_factions?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">新势力 ({{ previewData.new_factions.length }})</h4>
                      <div class="flex flex-wrap gap-2">
                        <span v-for="fac in previewData.new_factions" :key="fac.name" class="text-sm px-3 py-1 rounded-full" style="background-color: var(--md-error-container); color: var(--md-on-error-container);">
                          {{ fac.name }}
                        </span>
                      </div>
                    </div>

                    <!-- 伏笔统计 -->
                    <div v-if="previewData?.foreshadowing_plants?.length || previewData?.foreshadowing_payoffs?.length" class="mb-6">
                      <h4 class="md-title-medium font-semibold mb-3">伏笔规划</h4>
                      <div class="grid grid-cols-2 gap-4">
                        <div v-if="previewData?.foreshadowing_plants?.length" class="p-3 rounded-lg" style="background-color: var(--md-tertiary-container);">
                          <div class="font-semibold" style="color: var(--md-on-tertiary-container);">待埋设 ({{ previewData.foreshadowing_plants.length }})</div>
                          <ul class="mt-2 space-y-1 text-sm" style="color: var(--md-on-tertiary-container);">
                            <li v-for="(fp, idx) in displayedPlants" :key="idx">
                              第{{ fp.chapter_number }}章: {{ fp.content.slice(0, 30) }}{{ fp.content.length > 30 ? '...' : '' }}
                            </li>
                            <li v-if="previewData.foreshadowing_plants.length > 5" class="cursor-pointer hover:underline md-on-surface-variant" @click="showAllPlants = !showAllPlants">
                              {{ showAllPlants ? '收起' : `...还有 ${previewData.foreshadowing_plants.length - 5} 个 (点击展开)` }}
                            </li>
                          </ul>
                        </div>
                        <div v-if="previewData?.foreshadowing_payoffs?.length" class="p-3 rounded-lg" style="background-color: var(--md-secondary-container);">
                          <div class="font-semibold" style="color: var(--md-on-secondary-container);">计划回收 ({{ previewData.foreshadowing_payoffs.length }})</div>
                          <ul class="mt-2 space-y-1 text-sm" style="color: var(--md-on-secondary-container);">
                            <li v-for="(fp, idx) in displayedPayoffs" :key="idx">
                              第{{ fp.chapter_number }}章: {{ fp.content.slice(0, 30) }}{{ fp.content.length > 30 ? '...' : '' }}
                            </li>
                            <li v-if="previewData.foreshadowing_payoffs.length > 5" class="cursor-pointer hover:underline md-on-surface-variant" @click="showAllPayoffs = !showAllPayoffs">
                              {{ showAllPayoffs ? '收起' : `...还有 ${previewData.foreshadowing_payoffs.length - 5} 个 (点击展开)` }}
                            </li>
                          </ul>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="px-6 py-4 sm:flex sm:flex-row-reverse sm:px-8" style="background-color: var(--md-surface-container-low);">
                  <button type="button" class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center" @click="handleConfirm" :disabled="isConfirming">
                    {{ isConfirming ? '保存中...' : '确认保存' }}
                  </button>
                  <button type="button" class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3" @click="handleBack">返回修改</button>
                  <button type="button" class="md-btn md-btn-text md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3" @click="handleClose">取消</button>
                </div>
              </template>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import type { OutlinePreviewResponse } from '@/api/novel'

interface Props {
  show: boolean
  previewData: OutlinePreviewResponse | null
  isLoading: boolean
  isConfirming: boolean
}

const props = defineProps<Props>()
const emit = defineEmits(['close', 'preview', 'confirm', 'back'])

const numChapters = ref(5)
const userHint = ref('')
const showAllPlants = ref(false)
const showAllPayoffs = ref(false)

const isPreviewMode = computed(() => props.previewData !== null)

const displayedPlants = computed(() => {
  if (!props.previewData?.foreshadowing_plants) return []
  return showAllPlants.value
    ? props.previewData.foreshadowing_plants
    : props.previewData.foreshadowing_plants.slice(0, 5)
})

const displayedPayoffs = computed(() => {
  if (!props.previewData?.foreshadowing_payoffs) return []
  return showAllPayoffs.value
    ? props.previewData.foreshadowing_payoffs
    : props.previewData.foreshadowing_payoffs.slice(0, 5)
})

const setNumChapters = (count: number) => {
  numChapters.value = count
}

const handlePreview = () => {
  if (numChapters.value > 0) {
    emit('preview', numChapters.value, userHint.value.trim() || undefined)
  }
}

const handleConfirm = () => {
  emit('confirm')
}

const handleBack = () => {
  emit('back')
}

const handleClose = () => {
  userHint.value = ''
  showAllPlants.value = false
  showAllPayoffs.value = false
  emit('close')
}
</script>

<style scoped>
.m3-outline-dialog {
  border-radius: var(--md-radius-xl);
}

.m3-count-selected {
  background-color: var(--md-primary);
  color: var(--md-on-primary);
  border-color: transparent;
}
</style>
