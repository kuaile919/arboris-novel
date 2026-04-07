<template>
  <div class="p-8 bg-white rounded-2xl shadow-2xl fade-in">
    <h2 class="text-3xl font-bold text-center text-gray-800 mb-6">你的故事蓝图已生成！</h2>

    <div v-if="aiMessage" class="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
      <p class="text-blue-800">{{ aiMessage }}</p>
    </div>

    <div class="prose max-w-none p-6 bg-gray-50 rounded-lg border border-gray-200" v-html="formattedBlueprint"></div>

    <div v-if="isSaving" class="text-center py-8">
      <div class="relative mx-auto mb-6 w-16 h-16">
        <div class="absolute inset-0 border-4 border-green-100 rounded-full"></div>
        <div class="absolute inset-0 border-4 border-transparent border-t-green-500 rounded-full animate-spin"></div>
        <div class="absolute inset-2 bg-green-500 rounded-full flex items-center justify-center">
          <svg class="w-6 h-6 text-white animate-pulse" fill="currentColor" viewBox="0 0 20 20">
            <path d="M7.707 10.293a1 1 0 10-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L11 11.586V6a1 1 0 10-2 0v5.586l-1.293-1.293z"></path>
            <path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v1a1 1 0 11-2 0V4H7v1a1 1 0 11-2 0V4z"></path>
          </svg>
        </div>
      </div>

      <h3 class="text-lg font-semibold text-gray-800 mb-2 animate-pulse">正在保存蓝图...</h3>
      <p class="text-gray-600">即将跳转到写作工作台，继续完善章节与正文。</p>

      <div class="mt-4 w-32 mx-auto">
        <div class="w-full bg-gray-200 rounded-full h-1">
          <div class="h-1 bg-gradient-to-r from-green-400 to-green-600 rounded-full animate-pulse" style="width: 100%"></div>
        </div>
      </div>
    </div>

    <div v-else class="text-center mt-8 space-x-4">
      <button
        @click="confirmRegenerate"
        class="bg-gray-200 text-gray-700 font-bold py-3 px-8 rounded-full hover:bg-gray-300 transition-all duration-300 transform hover:scale-105"
      >
        <span class="flex items-center justify-center">
          <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"></path>
          </svg>
          重新生成
        </span>
      </button>
      <button
        @click="confirmBlueprint"
        :disabled="isSaving"
        class="bg-gradient-to-r from-green-500 to-emerald-600 text-white font-bold py-3 px-8 rounded-full hover:from-green-600 hover:to-emerald-700 transition-all duration-300 transform hover:scale-105 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
      >
        <span class="flex items-center justify-center">
          <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
          </svg>
          确认并开始创作
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { globalAlert } from '@/composables/useAlert'
import type { Blueprint } from '@/api/novel'

interface Props {
  blueprint: Blueprint | null
  aiMessage?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: []
  regenerate: []
}>()

const isSaving = ref(false)

const confirmRegenerate = async () => {
  const confirmed = await globalAlert.showConfirm('重新生成会覆盖当前蓝图，确定继续吗？', '重新生成确认')
  if (confirmed) {
    emit('regenerate')
  }
}

const confirmBlueprint = async () => {
  isSaving.value = true
  try {
    await emit('confirm')
  } finally {
    isSaving.value = false
  }
}

const escapeHtml = (value: unknown) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const safeText = (value: unknown, fallback = '待补充') => {
  const text = String(value ?? '').trim()
  return escapeHtml(text || fallback)
}

const createSection = (title: string, content: string, icon: string) => `
  <div class="mb-8 bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
    <div class="flex items-center mb-4">
      <div class="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center mr-3">
        ${icon}
      </div>
      <h3 class="text-xl font-bold text-gray-800">${title}</h3>
    </div>
    <div class="prose max-w-none text-gray-700">
      ${content}
    </div>
  </div>
`

const renderWorldSetting = (worldSetting: Record<string, any> | undefined) => {
  if (!worldSetting || typeof worldSetting !== 'object') {
    return '<p class="text-gray-500 italic">暂无世界设定信息</p>'
  }

  const sections: string[] = []

  if (worldSetting.core_rules) {
    sections.push(`
      <div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
        <h4 class="font-semibold text-amber-800 mb-2">核心规则</h4>
        <p class="text-amber-700">${safeText(worldSetting.core_rules)}</p>
      </div>
    `)
  }

  const locations = Array.isArray(worldSetting.key_locations) ? worldSetting.key_locations : []
  if (locations.length) {
    sections.push(`
      <div class="mb-4">
        <h4 class="font-semibold text-gray-800 mb-3">关键地点</h4>
        <div class="grid gap-3">
          ${locations
            .map(
              location => `
                <div class="bg-teal-50 border-l-4 border-teal-400 p-3 rounded-r-lg">
                  <h5 class="font-medium text-teal-800">${safeText(location?.name, '未命名地点')}</h5>
                  <p class="text-teal-700 text-sm mt-1">${safeText(location?.description)}</p>
                </div>
              `
            )
            .join('')}
        </div>
      </div>
    `)
  }

  const factions = Array.isArray(worldSetting.factions) ? worldSetting.factions : []
  if (factions.length) {
    sections.push(`
      <div>
        <h4 class="font-semibold text-gray-800 mb-3">主要势力</h4>
        <div class="grid gap-3">
          ${factions
            .map(
              faction => `
                <div class="bg-purple-50 border-l-4 border-purple-400 p-3 rounded-r-lg">
                  <h5 class="font-medium text-purple-800">${safeText(faction?.name, '未命名势力')}</h5>
                  <p class="text-purple-700 text-sm mt-1">${safeText(faction?.description)}</p>
                </div>
              `
            )
            .join('')}
        </div>
      </div>
    `)
  }

  return sections.join('') || '<p class="text-gray-500 italic">暂无世界设定信息</p>'
}

const renderCharacters = (characters: Array<Record<string, any>> | undefined) => {
  if (!Array.isArray(characters) || characters.length === 0) {
    return '<p class="text-gray-500 italic">暂无角色信息</p>'
  }

  return characters
    .map(character => {
      const name = safeText(character?.name, '未命名角色')
      const role = character?.role ? `<span class="bg-indigo-100 text-indigo-700 px-2 py-1 rounded-full text-xs font-medium">${safeText(character.role)}</span>` : ''

      const entries = [
        ['身份', character?.identity],
        ['性格', character?.personality],
        ['目标', character?.goals],
        ['能力', character?.abilities],
        ['与主角关系', character?.relationship_to_protagonist],
      ].filter(([, value]) => String(value ?? '').trim())

      return `
        <div class="bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-indigo-400 rounded-lg p-5 mb-4">
          <div class="flex items-center justify-between mb-3">
            <h4 class="text-lg font-bold text-indigo-800">${name}</h4>
            ${role}
          </div>
          <div class="space-y-3 text-sm">
            ${entries
              .map(
                ([label, value]) => `
                  <div class="bg-white/70 rounded-lg p-3">
                    <span class="font-medium text-gray-700 block mb-1">${label}</span>
                    <span class="text-gray-800">${safeText(value)}</span>
                  </div>
                `
              )
              .join('')}
          </div>
        </div>
      `
    })
    .join('')
}

const renderRelationships = (relationships: Array<Record<string, any>> | undefined) => {
  if (!Array.isArray(relationships) || relationships.length === 0) {
    return '<p class="text-gray-500 italic">暂无人物关系</p>'
  }

  return `
    <div class="space-y-3">
      ${relationships
        .map(
          relation => `
            <div class="bg-rose-50 border border-rose-200 rounded-lg p-4">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center">
                  <span class="font-medium text-rose-800 bg-white px-3 py-1 rounded-full text-sm shadow-sm">${safeText(relation?.character_from, '角色A')}</span>
                  <svg class="w-5 h-5 mx-3 text-rose-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M12.293 5.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-2.293-2.293a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                  </svg>
                  <span class="font-medium text-rose-800 bg-white px-3 py-1 rounded-full text-sm shadow-sm">${safeText(relation?.character_to, '角色B')}</span>
                </div>
              </div>
              <div class="text-sm text-rose-700 bg-white/60 rounded-lg p-3">
                <span class="font-medium">关系描述：</span>${safeText(relation?.description)}
              </div>
            </div>
          `
        )
        .join('')}
    </div>
  `
}

const formattedBlueprint = computed(() => {
  if (!props.blueprint) {
    return '<p class="text-center text-red-500">抱歉，蓝图生成失败，未能获取最终数据。</p>'
  }

  const blueprint = props.blueprint

  const icons = {
    summary:
      '<svg class="w-5 h-5 text-indigo-600" fill="currentColor" viewBox="0 0 20 20"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
    world:
      '<svg class="w-5 h-5 text-indigo-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clip-rule="evenodd"></path></svg>',
    characters:
      '<svg class="w-5 h-5 text-indigo-600" fill="currentColor" viewBox="0 0 20 20"><path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"></path></svg>',
    relationships:
      '<svg class="w-5 h-5 text-indigo-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" clip-rule="evenodd"></path></svg>',
  }

  const headerHTML = `
    <div class="text-center mb-8 p-6 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl text-white">
      <h1 class="text-4xl font-bold mb-4">${safeText(blueprint.title, '未命名标题')}</h1>
      <div class="flex flex-wrap justify-center gap-3 mb-4">
        <span class="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm font-medium">${safeText(blueprint.genre, '未指定题材')}</span>
        <span class="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm font-medium">${safeText(blueprint.style, '未指定风格')}</span>
        <span class="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm font-medium">${safeText(blueprint.tone, '未指定调性')}</span>
        <span class="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm font-medium">${safeText(blueprint.target_audience, '未指定读者')}</span>
        <span class="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-full text-sm font-medium">预计 ${Number(blueprint.total_chapters || 0)} 章</span>
      </div>
      <p class="text-sm text-white/80">章节大纲将在进入写作台后单独生成，这里先确认故事蓝图本身。</p>
    </div>
  `

  const summaryHTML = createSection(
    '故事梗概',
    `
      <div class="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-5 mb-4">
        <h4 class="font-semibold text-blue-800 mb-2">一句话总结</h4>
        <p class="text-lg italic text-blue-700">"${safeText(blueprint.one_sentence_summary)}"</p>
      </div>
      <div class="prose max-w-none">
        <h4 class="font-semibold text-gray-800 mb-3">完整简介</h4>
        <p class="text-gray-700 leading-relaxed">${safeText(blueprint.full_synopsis)}</p>
      </div>
    `,
    icons.summary
  )

  return `
    ${headerHTML}
    ${summaryHTML}
    ${createSection('世界设定', renderWorldSetting(blueprint.world_setting), icons.world)}
    ${createSection('主要角色', renderCharacters(blueprint.characters), icons.characters)}
    ${createSection('人物关系', renderRelationships(blueprint.relationships), icons.relationships)}
  `
})
</script>
