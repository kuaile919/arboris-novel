<!-- AIMETA P=关系区_角色关系展示|R=关系图谱|NR=不含编辑功能|E=component:RelationshipsSection|X=ui|A=关系组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-slate-900">人物关系</h2>
        <p class="text-sm text-slate-500">角色之间的纽带与冲突</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
          :class="viewMode === 'graph' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
          @click="viewMode = 'graph'">
          <svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
          </svg>
          图谱视图
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
          :class="viewMode === 'list' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
          @click="viewMode = 'list'">
          <svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          列表视图
        </button>
        <button
          v-if="editable"
          type="button"
          class="text-gray-400 hover:text-indigo-600 transition-colors"
          @click="emitEdit('relationships', '人物关系', data?.relationships)">
          <svg class="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
            <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
            <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 图谱视图 -->
    <div v-if="viewMode === 'graph'">
      <RelationshipGraph
        :relationships="relationships"
        :protagonists="protagonistNames"
      />
    </div>

    <!-- 列表视图 -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div
        v-for="(relation, index) in relationships"
        :key="index"
        class="bg-white/95 rounded-2xl border border-slate-200 shadow-sm p-6">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-semibold">
              {{ relation.character_from?.slice(0, 1) || '角' }}
            </div>
            <span class="font-semibold text-slate-900 truncate">{{ relation.character_from || '未知角色' }}</span>
          </div>
          <svg class="text-slate-400" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
          <div class="flex items-center space-x-3">
            <span class="font-semibold text-slate-900 truncate">{{ relation.character_to || '未知角色' }}</span>
            <div class="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 font-semibold">
              {{ relation.character_to?.slice(0, 1) || '角' }}
            </div>
          </div>
        </div>
        <div class="mt-4 bg-slate-50 border border-slate-100 rounded-xl p-4 text-center">
          <p class="text-sm font-semibold text-slate-700">{{ relation.relationship_type || '关系' }}</p>
          <p class="text-xs text-slate-500 leading-5 mt-1">{{ relation.description || '暂无描述' }}</p>
        </div>
      </div>
      <div v-if="!relationships.length" class="bg-white/95 rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-400">
        暂无人际关系信息
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import RelationshipGraph from '@/components/RelationshipGraph.vue'

interface RelationshipItem {
  character_from?: string
  character_to?: string
  relationship_type?: string
  description?: string
}

interface CharacterItem {
  name?: string
  identity?: string
  relationship_to_protagonist?: string
  is_protagonist?: boolean
}

const props = defineProps<{
  data: {
    relationships?: RelationshipItem[]
    characters?: CharacterItem[]
  } | null
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', payload: { field: string; title: string; value: any }): void
}>()

const viewMode = ref<'graph' | 'list'>('graph')

const relationships = computed(() => props.data?.relationships || [])

// 从角色数据中识别主角
const protagonistNames = computed(() => {
  const characters = props.data?.characters || []

  // 方法1: 使用 is_protagonist 字段明确标记的主角（支持多主角）
  const mains = characters
    .filter(c => c.is_protagonist === true && c.name)
    .map(c => c.name as string)
  if (mains.length > 0) return mains

  // 方法2: 查找身份包含"主角"、"主人公"等关键词的角色
  const mainByIdentity = characters
    .filter(c =>
    c.identity?.includes('主角') ||
    c.identity?.includes('主人公') ||
    c.identity?.includes('男主') ||
    c.identity?.includes('女主')
  )
    .map(c => c.name)
    .filter((name): name is string => Boolean(name))
  if (mainByIdentity.length > 0) return mainByIdentity

  // 方法3: 查找第一个角色（通常是主角）
  if (characters.length > 0 && characters[0].name) {
    return [characters[0].name]
  }

  // 方法4: 从关系数据中找出现频率最高的角色
  if (relationships.value.length > 0) {
    const charCount = new Map<string, number>()
    relationships.value.forEach(rel => {
      if (rel.character_from) {
        charCount.set(rel.character_from, (charCount.get(rel.character_from) || 0) + 1)
      }
      if (rel.character_to) {
        charCount.set(rel.character_to, (charCount.get(rel.character_to) || 0) + 1)
      }
    })
    const sorted = Array.from(charCount.entries()).sort((a, b) => b[1] - a[1])
    if (sorted.length > 0) return [sorted[0][0]]
  }

  return []
})

const emitEdit = (field: string, title: string, value: any) => {
  if (!props.editable) return
  emit('edit', { field, title, value })
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'RelationshipsSection'
})
</script>
