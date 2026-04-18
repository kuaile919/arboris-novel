<!-- AIMETA P=世界观区_世界设定展示|R=世界观信息|NR=不含编辑功能|E=component:WorldSettingSection|X=ui|A=世界观组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-6">
    <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
      <div class="flex items-start justify-between gap-4 mb-4">
        <h3 class="text-lg font-semibold text-slate-900">核心规则</h3>
        <button
          v-if="editable"
          type="button"
          class="text-gray-400 hover:text-indigo-600 transition-colors"
          @click="emitEdit('world_setting.core_rules', '核心规则', worldSetting.core_rules)">
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
            <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <p class="text-slate-600 leading-7 whitespace-pre-line">{{ worldSetting.core_rules || '暂无' }}</p>
    </div>

    <div v-if="extraWorldSettings.length" class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
      <div class="flex items-center justify-between gap-4 mb-4">
        <h3 class="text-lg font-semibold text-slate-900">扩展设定</h3>
      </div>
      <ul class="space-y-4">
        <li
          v-for="item in extraWorldSettings"
          :key="item.key"
          class="bg-slate-50 border border-slate-100 rounded-xl p-4"
        >
          <div class="flex items-center justify-between gap-3 mb-2">
            <strong class="text-slate-800">{{ item.label }}</strong>
            <button
              v-if="editable"
              type="button"
              class="text-gray-400 hover:text-indigo-600 transition-colors"
              @click="emitEdit(`world_setting.${item.key}`, item.label, item.raw)"
            >
              <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
                <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>
          <pre v-if="item.multiline" class="text-xs text-slate-600 whitespace-pre-wrap leading-6">{{ item.text }}</pre>
          <p v-else class="text-sm text-slate-600 leading-6 whitespace-pre-wrap">{{ item.text }}</p>
        </li>
      </ul>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 关键地点 -->
      <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center text-slate-900 font-semibold">
            <svg class="mr-2 text-indigo-500" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18"/><path d="M6 18H4a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h2v7Z"/><path d="M18 18h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2h-2v7Z"/></svg>
            <span>关键地点</span>
          </div>
          <div class="flex items-center gap-2">
            <!-- 同步按钮 -->
            <button
              v-if="editable"
              type="button"
              :disabled="syncLoading"
              :class="syncLoading ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:text-indigo-600'"
              class="transition-colors"
              title="从章节内容同步"
              @click="handleSync"
            >
              <svg :class="['h-5 w-5', { 'animate-spin': syncLoading }]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>
                <path d="M21 3v5h-5"/>
              </svg>
            </button>
            <!-- 编辑按钮 -->
            <button
              v-if="editable"
              type="button"
              class="text-gray-400 hover:text-indigo-600 transition-colors"
              @click="emitEdit('key_locations', '关键地点', props.data?.key_locations)">
              <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
                <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
        <ul class="space-y-4 text-sm text-slate-600">
          <li v-for="(item, index) in locations" :key="index" class="bg-slate-50 border border-slate-100 rounded-xl p-4">
            <div class="flex items-start justify-between gap-2">
              <strong class="block text-slate-800 mb-1">{{ item.title }}</strong>
              <span v-if="item.first_appear_chapter" class="text-xs text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full whitespace-nowrap">
                第{{ item.first_appear_chapter }}章
              </span>
            </div>
            <span class="text-xs text-slate-500 leading-5">{{ item.description }}</span>
          </li>
          <li v-if="!locations.length" class="text-slate-400 text-sm">暂无数据</li>
        </ul>
      </div>

      <!-- 主要阵营 -->
      <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center text-slate-900 font-semibold">
            <svg class="mr-2 text-indigo-500" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>主要阵营</span>
          </div>
          <div class="flex items-center gap-2">
            <!-- 同步按钮 -->
            <button
              v-if="editable"
              type="button"
              :disabled="syncLoading"
              :class="syncLoading ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:text-indigo-600'"
              class="transition-colors"
              title="从章节内容同步"
              @click="handleSync"
            >
              <svg :class="['h-5 w-5', { 'animate-spin': syncLoading }]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>
                <path d="M21 3v5h-5"/>
              </svg>
            </button>
            <!-- 编辑按钮 -->
            <button
              v-if="editable"
              type="button"
              class="text-gray-400 hover:text-indigo-600 transition-colors"
              @click="emitEdit('factions', '主要阵营', props.data?.factions)">
              <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
                <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
        <ul class="space-y-4 text-sm text-slate-600">
          <li v-for="(item, index) in factions" :key="index" class="bg-slate-50 border border-slate-100 rounded-xl p-4">
            <div class="flex items-start justify-between gap-2">
              <strong class="block text-slate-800 mb-1">{{ item.title }}</strong>
              <span v-if="item.first_appear_chapter" class="text-xs text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full whitespace-nowrap">
                第{{ item.first_appear_chapter }}章
              </span>
            </div>
            <span class="text-xs text-slate-500 leading-5">{{ item.description }}</span>
          </li>
          <li v-if="!factions.length" class="text-slate-400 text-sm">暂无数据</li>
        </ul>
      </div>
    </div>

    <!-- 同步结果提示 -->
    <div
      v-if="syncResult"
      class="fixed bottom-6 right-6 bg-white rounded-xl shadow-lg border border-slate-200 p-4 max-w-sm z-50"
    >
      <div class="flex items-start gap-3">
        <svg
          :class="['h-5 w-5 mt-0.5', syncResult.added_count > 0 ? 'text-green-500' : 'text-blue-500']"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path v-if="syncResult.added_count > 0" fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
          <path v-else fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
        </svg>
        <div class="flex-1">
          <p class="text-sm font-medium text-slate-900">
            {{ syncResult.added_count > 0 ? '同步完成' : '暂无新内容' }}
          </p>
          <p class="text-xs text-slate-500 mt-1">
            <template v-if="syncResult.added_count > 0">
              新增 {{ syncResult.new_locations?.length || 0 }} 个地点，{{ syncResult.new_factions?.length || 0 }} 个阵营
              <br>
              总计：{{ syncResult.total_locations }} 个地点，{{ syncResult.total_factions }} 个阵营
            </template>
            <template v-else>
              未从章节中提取到新的地点或阵营
              <br>
              当前总计：{{ syncResult.total_locations }} 个地点，{{ syncResult.total_factions }} 个阵营
            </template>
          </p>
        </div>
        <button @click="syncResult = null" class="text-gray-400 hover:text-gray-600">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { NovelAPI, type SyncWorldSettingResult } from '@/api/novel'

interface ListItem {
  title: string
  description: string
}

const props = defineProps<{
  data: Record<string, any> | null
  editable?: boolean
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'edit', payload: { field: string; title: string; value: any }): void
  (e: 'synced'): void
}>()

const worldSetting = computed(() => props.data?.world_setting || {})

const EXTRA_FIELD_LABELS: Record<string, string> = {
  currency_system: '货币体系',
  current_system: '货币体系（旧字段）',
  power_system: '力量体系',
  magic_system: '法术体系',
  cultivation_system: '修炼体系',
  social_rules: '社会规则',
  taboo_rules: '禁忌规则',
}

// 同步状态
const syncLoading = ref(false)
const syncResult = ref<SyncWorldSettingResult | null>(null)

const normalizeList = (source: any): ListItem[] => {
  if (!source) return []
  if (Array.isArray(source)) {
    return source.map((item: any) => {
      if (typeof item === 'string') {
        const [title, ...rest] = item.split('：')
        return {
          title: title || item,
          description: rest.join('：') || '暂无描述'
        }
      }
      return {
        title: item?.name || '未命名',
        description: item?.description || item?.details || '暂无描述'
      }
    })
  }
  return []
}

const normalizeListWithChapter = (source: any): LocationItem[] => {
  if (!source) return []
  if (Array.isArray(source)) {
    return source.map((item: any) => {
      if (typeof item === 'string') {
        const [title, ...rest] = item.split('：')
        return {
          title: title || item,
          description: rest.join('：') || '暂无描述'
        }
      }
      return {
        title: item?.name || '未命名',
        description: item?.description || item?.details || '暂无描述',
        first_appear_chapter: item?.first_appear_chapter
      }
    })
  }
  return []
}

interface LocationItem extends ListItem {
  first_appear_chapter?: number
}

const isEmptyValue = (value: any) => {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

const formatExtraFieldLabel = (key: string) => {
  return EXTRA_FIELD_LABELS[key] || key.replace(/_/g, ' ')
}

const formatExtraFieldValue = (value: any) => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch (error) {
    return String(value ?? '')
  }
}

const extraWorldSettings = computed(() => {
  const ws = worldSetting.value
  const ignored = new Set(['core_rules', 'key_locations', 'factions', 'locations', 'location'])
  return Object.entries(ws)
    .filter(([key, value]) => !ignored.has(key) && !isEmptyValue(value))
    .map(([key, value]) => {
      const text = formatExtraFieldValue(value)
      return {
        key,
        label: formatExtraFieldLabel(key),
        text,
        multiline: typeof value === 'object' || text.includes('\n') || text.length > 120,
        raw: value,
      }
    })
})

const locations = computed(() => {
  return normalizeListWithChapter(props.data?.key_locations || [])
})
const factions = computed(() => {
  return normalizeListWithChapter(props.data?.factions || [])
})

const emitEdit = (field: string, title: string, value: any) => {
  if (!props.editable) return
  emit('edit', { field, title, value })
}

// 同步处理
const handleSync = async () => {
  if (!props.projectId || syncLoading.value) return

  syncLoading.value = true
  syncResult.value = null

  try {
    const result = await NovelAPI.syncWorldSetting(props.projectId)
    syncResult.value = result
    emit('synced')

    // 5秒后自动关闭提示
    setTimeout(() => {
      syncResult.value = null
    }, 5000)
  } catch (error) {
    console.error('同步失败:', error)
    alert('同步失败: ' + (error as Error).message)
  } finally {
    syncLoading.value = false
  }
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'WorldSettingSection'
})
</script>
