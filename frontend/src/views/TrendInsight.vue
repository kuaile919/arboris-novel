<!-- AIMETA P=市场风向页面_网文排行榜和趋势分析|R=排行榜展示_趋势分析_数据刷新|NR=不含API调用|E=route:/trends#component:TrendInsight|X=ui|A=页面组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="min-h-screen p-4 md:p-6 max-w-7xl mx-auto">
    <!-- 顶部导航 -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <button @click="goBack" class="text-gray-500 hover:text-gray-800 transition-colors">
          <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 class="text-2xl font-bold text-gray-800">市场风向</h1>
          <p class="text-xs text-gray-500 mt-0.5">
            数据来源: {{ dataSourceText }} | 更新于: {{ lastUpdateText }}
            <span v-if="qualityScore > 0" class="ml-2" :class="qualityColorClass">
              质量: {{ Math.round(qualityScore * 100) }}%
            </span>
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="refreshData"
          :disabled="isLoading || isRefreshing"
          class="px-4 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
        >
          {{ isRefreshing ? '刷新中...' : '刷新数据' }}
        </button>
        <button
          @click="showImportModal = true"
          class="px-4 py-2 text-sm bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition"
        >
          手动导入
        </button>
        <div class="relative">
          <button
            @click="showDeleteMenu = !showDeleteMenu"
            class="px-4 py-2 text-sm bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition"
          >
            删除数据
          </button>
          <div
            v-if="showDeleteMenu"
            class="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50"
          >
            <div class="p-2 text-xs text-gray-500 border-b border-gray-100">选择平台删除全部数据</div>
            <button
              @click="handleDeletePlatform('qidian')"
              class="w-full px-4 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
            >
              <span class="w-2 h-2 bg-blue-500 rounded-full"></span>
              起点中文网
            </button>
            <button
              @click="handleDeletePlatform('fanqie')"
              class="w-full px-4 py-2 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
            >
              <span class="w-2 h-2 bg-red-500 rounded-full"></span>
              番茄小说
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 平台选择 -->
    <div class="flex gap-2 mb-6">
      <button
        v-for="p in platforms"
        :key="p.id"
        @click="selectPlatform(p.id)"
        :class="[
          'px-5 py-2.5 rounded-full text-sm font-medium transition-all',
          currentPlatform === p.id
            ? 'bg-indigo-500 text-white shadow-md'
            : 'bg-white text-gray-600 border border-gray-200 hover:border-indigo-300'
        ]"
      >
        {{ p.name }}
      </button>
    </div>

    <!-- 加载状态 -->
    

    <!-- 主内容 -->
    <div>
      <!-- 榜单分类切换 -->
      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 mb-6">
        <template v-if="isFanqiePlatform">
          <div class="flex flex-col gap-1 mb-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 class="text-sm font-semibold text-gray-800">番茄分类排行</h3>
              <p class="text-xs text-gray-500">按番茄首页实际分类切换，并展示当前题材的阅读榜和新书榜</p>
            </div>
            <span v-if="currentCategoryName" class="text-xs font-medium text-indigo-600">
              当前: {{ currentFanqieGenderLabel }} / {{ currentCategoryName }}
            </span>
          </div>

          <div class="flex gap-3 mb-4">
            <button
              v-for="(name, key) in fanqieGenderTabs"
              :key="key"
              @click="selectFanqieGender(key)"
              :class="[
                'rounded-full border px-5 py-2 text-sm font-medium transition-all',
                currentFanqieGender === key
                  ? 'border-gray-900 bg-gray-900 text-white shadow-sm'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-indigo-300 hover:text-indigo-600'
              ]"
            >
              {{ name }}
            </button>
          </div>

          <div class="flex gap-3 overflow-x-auto pb-1">
            <button
              v-for="(name, key) in currentFanqieCategories"
              :key="key"
              @click="selectCategory(String(key))"
              :class="[
                'whitespace-nowrap rounded-full border px-4 py-2 text-sm font-medium transition-all',
                currentFanqieCategoryId === String(key)
                  ? 'border-orange-500 bg-orange-500 text-white shadow-sm'
                  : 'border-gray-200 bg-gray-50 text-gray-600 hover:border-orange-300 hover:text-orange-600'
              ]"
            >
              {{ name }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex flex-col gap-1 mb-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 class="text-sm font-semibold text-gray-800">主要排行榜</h3>
              <p class="text-xs text-gray-500">按平台官方榜单展示主要排行</p>
            </div>
            <span v-if="currentCategoryName" class="text-xs font-medium text-indigo-600">
              当前: {{ currentCategoryName }}
            </span>
          </div>

          <div class="flex gap-3 overflow-x-auto pb-1">
            <button
              v-for="(name, key) in currentCategories"
              :key="String(key)"
              @click="selectCategory(String(key))"
              :class="[
                'min-w-[108px] rounded-2xl border px-4 py-3 text-sm font-medium transition-all',
                currentCategory === String(key)
                  ? 'border-gray-900 bg-gray-900 text-white shadow-sm'
                  : 'border-gray-200 bg-gray-50 text-gray-600 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-600'
              ]"
            >
              {{ name }}
            </button>
          </div>
        </template>
      </div>

      <!-- 概览区：题材分布 + 热门关键词 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <!-- 题材分布 -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 class="text-sm font-semibold text-gray-700 mb-4">题材分布</h3>
          <div v-if="isLoading" class="space-y-3">
            <div v-for="idx in 6" :key="`genre-skeleton-${idx}`" class="flex items-center gap-3 animate-pulse">
              <div class="h-4 w-12 rounded bg-gray-100 shrink-0"></div>
              <div class="flex-1 h-6 rounded-full bg-gray-100"></div>
              <div class="h-4 w-8 rounded bg-gray-100 shrink-0"></div>
            </div>
          </div>
          <div v-else-if="Object.keys(genreDistribution.genres || {}).length > 0" class="space-y-2">
            <div
              v-for="(data, genre) in sortedGenres"
              :key="String(genre)"
              class="flex items-center gap-3"
            >
              <span class="text-xs text-gray-500 w-16 text-right shrink-0">{{ genre }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :style="{ width: (data as any).percentage + '%', backgroundColor: getGenreColor(String(genre)) }"
                ></div>
              </div>
              <span class="text-xs text-gray-500 w-10 text-right">{{ (data as any).count }}本</span>
            </div>
          </div>
          <div v-else class="text-center text-gray-400 text-sm py-4">暂无数据</div>
        </div>

        <!-- 热门关键词 -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 class="text-sm font-semibold text-gray-700 mb-4">热门关键词</h3>
          <div v-if="isReportLoading" class="flex flex-wrap gap-2">
            <span
              v-for="idx in 8"
              :key="`keyword-skeleton-${idx}`"
              class="inline-block h-7 rounded-full bg-indigo-50 animate-pulse"
              :class="idx % 3 === 0 ? 'w-20' : idx % 2 === 0 ? 'w-16' : 'w-12'"
            ></span>
          </div>
          <div v-else-if="trendReport.hot_keywords && trendReport.hot_keywords.length > 0" class="flex flex-wrap gap-2">
            <span
              v-for="keyword in trendReport.hot_keywords"
              :key="keyword"
              class="inline-block px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-medium"
            >
              {{ keyword }}
            </span>
          </div>
          <div v-else class="text-center text-gray-400 text-sm py-4">暂无数据</div>
        </div>
      </div>

      <!-- AI 趋势报告 -->
      <div v-if="isReportLoading || displayTrendSummary" class="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl shadow-sm border border-indigo-100 p-5 mb-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-indigo-800">AI 趋势分析</h3>
          <span class="text-xs text-indigo-500">{{ isReportLoading ? '分析中...' : formatDate(trendReport.report_date) }}</span>
        </div>
        <template v-if="isReportLoading">
          <div class="space-y-3 animate-pulse">
            <div class="h-4 w-full rounded bg-white/70"></div>
            <div class="h-4 w-11/12 rounded bg-white/70"></div>
            <div class="h-4 w-10/12 rounded bg-white/70"></div>
            <div class="h-4 w-8/12 rounded bg-white/70"></div>
          </div>
        </template>
        <template v-else>
          <p class="text-sm text-gray-700 leading-relaxed mb-4">{{ displayTrendSummary }}</p>

          <div v-if="trendReport.creation_suggestions && trendReport.creation_suggestions.length > 0">
            <h4 class="text-xs font-semibold text-indigo-700 mb-2">创作建议</h4>
            <ul class="space-y-1">
              <li v-for="(suggestion, idx) in trendReport.creation_suggestions" :key="idx" class="text-xs text-gray-600 flex items-start gap-2">
                <span class="text-indigo-400 mt-0.5">{{ idx + 1 }}.</span>
                <span>{{ suggestion }}</span>
              </li>
            </ul>
          </div>

          <div class="flex justify-end mt-4">
            <button
              @click="startCreation"
              class="px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition shadow-md"
            >
              基于风向创作
            </button>
          </div>
        </template>
      </div>

      <!-- 排行榜列表 -->
      <div v-if="isFanqiePlatform" class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div class="px-5 py-3 border-b border-gray-100 bg-gray-50">
            <h3 class="text-sm font-semibold text-gray-700">
              {{ fanqieReadTitle }}
              <span class="text-xs text-gray-400 font-normal ml-2">共 {{ rankingBooks.length }} 本</span>
            </h3>
          </div>

          <div v-if="isLoading" class="divide-y divide-gray-50">
            <div
              v-for="idx in 6"
              :key="`fanqie-read-skeleton-${idx}`"
              class="px-5 py-3 flex items-center gap-4 animate-pulse"
            >
              <div class="w-8 h-8 rounded-full bg-gray-100 shrink-0"></div>
              <div class="flex-1 min-w-0 space-y-2">
                <div class="h-4 w-40 rounded bg-gray-100"></div>
                <div class="h-3 w-24 rounded bg-gray-100"></div>
                <div class="h-3 w-5/6 rounded bg-gray-100"></div>
              </div>
              <div class="h-4 w-10 rounded bg-gray-100 shrink-0"></div>
            </div>
          </div>
          <div v-else-if="rankingBooks.length === 0" class="text-center text-gray-400 text-sm py-10">
            暂无 {{ fanqieReadTitle }} 数据
          </div>

          <div v-else class="divide-y divide-gray-50">
            <div
              v-for="book in rankingBooks"
              :key="`read-${book.rank}`"
              class="px-5 py-3 hover:bg-gray-50 transition flex items-center gap-4"
            >
              <span :class="[
                'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
                book.rank <= 3 ? 'bg-amber-400 text-white' : 'bg-gray-200 text-gray-500'
              ]">
                {{ book.rank }}
              </span>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-800 truncate">{{ book.title }}</span>
                  <span v-if="book.genre" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded shrink-0">{{ book.genre }}</span>
                </div>
                <div class="flex items-center gap-3 text-xs text-gray-400">
                  <span>{{ book.author }}</span>
                  <span v-if="book.word_count">{{ book.word_count }}字</span>
                </div>
                <p v-if="book.description" class="text-xs text-gray-500 mt-1 line-clamp-2">{{ book.description }}</p>
              </div>

              <div class="flex items-center gap-1 shrink-0">
                <span class="text-xs text-orange-500 font-medium">{{ book.heat_score || '-' }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div class="px-5 py-3 border-b border-gray-100 bg-gray-50">
            <h3 class="text-sm font-semibold text-gray-700">
              {{ fanqieNewTitle }}
              <span class="text-xs text-gray-400 font-normal ml-2">共 {{ fanqieNewBooks.length }} 本</span>
            </h3>
          </div>

          <div v-if="isLoading" class="divide-y divide-gray-50">
            <div
              v-for="idx in 6"
              :key="`fanqie-new-skeleton-${idx}`"
              class="px-5 py-3 flex items-center gap-4 animate-pulse"
            >
              <div class="w-8 h-8 rounded-full bg-gray-100 shrink-0"></div>
              <div class="flex-1 min-w-0 space-y-2">
                <div class="h-4 w-40 rounded bg-gray-100"></div>
                <div class="h-3 w-24 rounded bg-gray-100"></div>
                <div class="h-3 w-5/6 rounded bg-gray-100"></div>
              </div>
              <div class="h-4 w-10 rounded bg-gray-100 shrink-0"></div>
            </div>
          </div>
          <div v-else-if="fanqieNewBooks.length === 0" class="text-center text-gray-400 text-sm py-10">
            暂无 {{ fanqieNewTitle }} 数据
          </div>

          <div v-else class="divide-y divide-gray-50">
            <div
              v-for="book in fanqieNewBooks"
              :key="`new-${book.rank}`"
              class="px-5 py-3 hover:bg-gray-50 transition flex items-center gap-4"
            >
              <span :class="[
                'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
                book.rank <= 3 ? 'bg-amber-400 text-white' : 'bg-gray-200 text-gray-500'
              ]">
                {{ book.rank }}
              </span>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-800 truncate">{{ book.title }}</span>
                  <span v-if="book.genre" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded shrink-0">{{ book.genre }}</span>
                </div>
                <div class="flex items-center gap-3 text-xs text-gray-400">
                  <span>{{ book.author }}</span>
                  <span v-if="book.word_count">{{ book.word_count }}字</span>
                </div>
                <p v-if="book.description" class="text-xs text-gray-500 mt-1 line-clamp-2">{{ book.description }}</p>
              </div>

              <div class="flex items-center gap-1 shrink-0">
                <span class="text-xs text-orange-500 font-medium">{{ book.heat_score || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="px-5 py-3 border-b border-gray-100 bg-gray-50">
          <h3 class="text-sm font-semibold text-gray-700">
            {{ currentCategoryName || '排行榜' }}
            <span class="text-xs text-gray-400 font-normal ml-2">共 {{ rankingBooks.length }} 本</span>
          </h3>
        </div>

        <div v-if="isLoading" class="divide-y divide-gray-50">
          <div
            v-for="idx in 8"
            :key="`qidian-skeleton-${idx}`"
            class="px-5 py-3 flex items-center gap-4 animate-pulse"
          >
            <div class="w-8 h-8 rounded-full bg-gray-100 shrink-0"></div>
            <div class="flex-1 min-w-0 space-y-2">
              <div class="h-4 w-48 rounded bg-gray-100"></div>
              <div class="h-3 w-24 rounded bg-gray-100"></div>
              <div class="h-3 w-2/3 rounded bg-gray-100"></div>
            </div>
            <div class="h-4 w-10 rounded bg-gray-100 shrink-0"></div>
          </div>
        </div>
        <div v-else-if="rankingBooks.length === 0" class="text-center text-gray-400 text-sm py-10">
          暂无 {{ currentCategoryName || '排行榜' }} 数据，点击"刷新数据"获取最新排行
        </div>

        <div v-else class="divide-y divide-gray-50">
          <div
            v-for="book in rankingBooks"
            :key="book.rank"
            class="px-5 py-3 hover:bg-gray-50 transition flex items-center gap-4"
          >
            <span :class="[
              'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
              book.rank <= 3 ? 'bg-amber-400 text-white' : 'bg-gray-200 text-gray-500'
            ]">
              {{ book.rank }}
            </span>

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-gray-800 truncate">{{ book.title }}</span>
                <span v-if="book.genre" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded shrink-0">{{ book.genre }}</span>
              </div>
              <div class="flex items-center gap-3 text-xs text-gray-400">
                <span>{{ book.author }}</span>
                <span v-if="book.word_count">{{ book.word_count }}字</span>
              </div>
              <p v-if="book.description" class="text-xs text-gray-500 mt-1 line-clamp-1">{{ book.description }}</p>
            </div>

            <div class="flex items-center gap-1 shrink-0">
              <span class="text-xs text-orange-500 font-medium">{{ book.heat_score || '-' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 手动导入弹窗 -->
    <div v-if="showImportModal" class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" @click.self="showImportModal = false">
      <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col" @click.stop>
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-bold text-gray-800">手动导入排行榜</h2>
        </div>
        <div class="px-6 py-4 flex-1 overflow-y-auto">
          <p class="text-sm text-gray-500 mb-3">
            粘贴排行榜数据，支持以下格式：
            <br/>- 每行一条：排名. 书名 作者
            <br/>- JSON数组
            <br/>- 自由文本
          </p>
          <textarea
            v-model="importText"
            rows="10"
            class="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300"
            placeholder="1. 深空彼岸 张三&#10;2. 星际征途 李四&#10;3. ..."
          ></textarea>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button @click="showImportModal = false" class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">取消</button>
          <button @click="handleImport" :disabled="!importText.trim()" class="px-4 py-2 text-sm bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition disabled:opacity-50">
            导入
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { TrendAPI } from '@/api/trend'
import type { RankingBook, TrendReport, PlatformInfo, GenreDistribution } from '@/api/trend'
import { globalAlert } from '@/composables/useAlert'

const router = useRouter()

type FanqieGenderKey = 'male' | 'female'
type FanqieCategoryGroupMap = Record<string, Record<string, string>>
type FanqieGenderTabMap = Record<string, string>

// 状态
const platforms = ref<PlatformInfo[]>([])
const currentPlatform = ref('qidian')
const currentCategory = ref('hot')
const currentFanqieGender = ref<FanqieGenderKey>('male')
const currentFanqieCategoryId = ref('1141')
const isLoading = ref(false)
const isReportLoading = ref(false)
const isRefreshing = ref(false)
const rankingBooks = ref<RankingBook[]>([])
const fanqieNewBooks = ref<RankingBook[]>([])
const genreDistribution = ref<GenreDistribution>({ genres: {}, total: 0, snapshot_date: null })
const trendReport = ref<TrendReport>({} as TrendReport)
const showImportModal = ref(false)
const importText = ref('')
const showDeleteMenu = ref(false)
let loadRequestId = 0

const fanqieFallbackMeta: {
  gender_tabs: FanqieGenderTabMap
  category_groups: FanqieCategoryGroupMap
  ranking_types: Record<string, string>
} = {
  gender_tabs: {
    male: '男频排行榜',
    female: '女频排行榜',
  },
  category_groups: {
    male: {
      '1141': '西方奇幻',
      '1140': '东方仙侠',
      '8': '科幻末世',
      '261': '都市日常',
      '124': '都市修真',
      '1014': '都市高武',
      '273': '历史古代',
      '27': '战神赘婿',
      '263': '都市种田',
      '258': '传统玄幻',
      '272': '历史脑洞',
      '539': '悬疑脑洞',
      '262': '都市脑洞',
      '257': '玄幻脑洞',
      '751': '悬疑灵异',
      '504': '抗战谍战',
      '746': '游戏体育',
      '718': '动漫衍生',
      '1016': '男频衍生',
    },
    female: {
      '1139': '古风世情',
      '8': '科幻末世',
      '746': '游戏体育',
      '1015': '女频衍生',
      '248': '玄幻言情',
      '23': '种田',
      '79': '年代',
      '267': '现言脑洞',
      '246': '宫斗宅斗',
      '539': '悬疑脑洞',
      '253': '古言脑洞',
      '24': '快穿',
      '749': '青春甜宠',
      '745': '星光璀璨',
      '747': '女频悬疑',
      '750': '职场婚恋',
      '748': '豪门总裁',
      '1017': '民国言情',
    },
  },
  ranking_types: {
    read: '阅读榜',
    new: '新书榜',
  },
}

// 计算属性
const currentPlatformInfo = computed(() => {
  return platforms.value.find(p => p.id === currentPlatform.value)
})

const isFanqiePlatform = computed(() => currentPlatform.value === 'fanqie')

const currentCategories = computed(() => {
  return currentPlatformInfo.value?.categories || {}
})

const fanqieMeta = computed(() => {
  return currentPlatformInfo.value?.meta || fanqieFallbackMeta
})

const fanqieGenderTabs = computed<FanqieGenderTabMap>(() => {
  return fanqieMeta.value.gender_tabs || fanqieFallbackMeta.gender_tabs
})

const fanqieCategoryGroups = computed<FanqieCategoryGroupMap>(() => {
  return fanqieMeta.value.category_groups || fanqieFallbackMeta.category_groups
})

const currentFanqieCategories = computed(() => {
  return fanqieCategoryGroups.value[currentFanqieGender.value] || {}
})

const currentFanqieGenderLabel = computed(() => {
  return fanqieGenderTabs.value[currentFanqieGender.value] || currentFanqieGender.value
})

const fanqieReadCategoryKey = computed(() => {
  return `${currentFanqieGender.value}:${currentFanqieCategoryId.value}:read`
})

const fanqieNewCategoryKey = computed(() => {
  return `${currentFanqieGender.value}:${currentFanqieCategoryId.value}:new`
})

const currentFanqieCategoryName = computed(() => {
  return currentFanqieCategories.value[currentFanqieCategoryId.value] || ''
})

const currentCategoryName = computed(() => {
  if (isFanqiePlatform.value) return currentFanqieCategoryName.value
  return currentCategories.value[currentCategory.value] || ''
})

const currentReportCategory = computed(() => {
  return isFanqiePlatform.value ? 'all' : currentCategory.value
})

const fanqieReadTitle = computed(() => {
  return currentFanqieCategoryName.value ? `${currentFanqieCategoryName.value}·阅读榜` : '阅读榜'
})

const fanqieNewTitle = computed(() => {
  return currentFanqieCategoryName.value ? `${currentFanqieCategoryName.value}·新书榜` : '新书榜'
})

const sortedGenres = computed(() => {
  const genres = genreDistribution.value.genres
  if (!genres) return {} as Record<string, any>
  return Object.entries(genres)
    .sort(([, a], [, b]) => ((b as any).percentage as number) - ((a as any).percentage as number))
    .reduce((acc, [key, val]) => ({ ...acc, [key]: val }), {} as Record<string, any>)
})

const displayTrendSummary = computed(() => {
  return extractTrendSummary(trendReport.value.trend_summary, trendReport.value.ai_full_report)
})

// 数据质量相关计算属性
const qualityScore = computed(() => {
  // 从报告中获取质量分数，或使用书籍数据计算
  const books = isFanqiePlatform.value ? [...rankingBooks.value, ...fanqieNewBooks.value] : rankingBooks.value
  if (!books || books.length === 0) return 0

  let totalScore = 0
  books.forEach(book => {
    let score = 0
    if (book.genre) score += 0.3
    if (book.tags) score += 0.2
    if (book.description && book.description.length > 10) score += 0.2
    if (book.author) score += 0.2
    if (book.word_count) score += 0.1
    totalScore += score
  })

  return totalScore / books.length
})

const qualityColorClass = computed(() => {
  const score = qualityScore.value
  if (score >= 0.8) return 'text-green-600'
  if (score >= 0.5) return 'text-yellow-600'
  return 'text-red-500'
})

const dataSourceText = computed(() => {
  // 根据数据质量判断数据来源
  const score = qualityScore.value
  if (score >= 0.7) return '自动抓取'
  if (score >= 0.3) return '自动+补全'
  return '手动导入'
})

const lastUpdateText = computed(() => {
  const date = genreDistribution.value?.snapshot_date
  if (!date) return '未知'

  const updateTime = new Date(date)
  const now = new Date()
  const diffMs = now.getTime() - updateTime.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))

  if (diffHours < 1) return '刚刚'
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffHours < 48) return '昨天'
  return updateTime.toLocaleDateString('zh-CN')
})

// 颜色映射
const genreColors: Record<string, string> = {
  '玄幻': '#6366f1', '仙侠': '#8b5cf6', '都市': '#3b82f6',
  '历史': '#f59e0b', '军事': '#ef4444', '悬疑': '#64748b',
  '科幻': '#06b6d4', '游戏': '#10b981', '体育': '#14b8a6',
  '灵异': '#a855f7', '同人': '#ec4899', '武侠': '#f97316',
  '奇幻': '#7c3aed', '二次元': '#d946ef', '现实': '#84cc16',
}
function getGenreColor(genre: string): string {
  return genreColors[genre] || '#6b7280'
}

function looksLikeStructuredTrendPayload(value?: string): boolean {
  const text = value?.trim()
  if (!text) return false

  return (
    text.startsWith('{') ||
    text.startsWith('```json') ||
    text.startsWith('```') ||
    (text.includes('"summary"') && (text.includes('"genre_distribution"') || text.includes('"hot_keywords"')))
  )
}

function decodeJsonStringValue(value: string): string {
  try {
    return JSON.parse(`"${value}"`).trim()
  } catch {
    return value.replace(/\\n/g, '\n').replace(/\\r/g, '').replace(/\\"/g, '"').trim()
  }
}

function extractJsonStringField(text: string, fieldName: string): string {
  const match = text.match(new RegExp(`"${fieldName}"\\s*:\\s*"`, 'm'))
  if (!match || match.index === undefined) return ''

  const start = match.index + match[0].length
  let escaped = false
  let value = ''

  for (let i = start; i < text.length; i += 1) {
    const ch = text[i]
    if (escaped) {
      value += ch
      escaped = false
      continue
    }
    if (ch === '\\') {
      value += ch
      escaped = true
      continue
    }
    if (ch === '"') {
      break
    }
    value += ch
  }

  return decodeJsonStringValue(value)
}

function normalizeTrendSummary(value?: string): string {
  const text = value?.trim()
  if (!text) return ''
  if (!looksLikeStructuredTrendPayload(text)) return text
  return extractJsonStringField(text, 'summary')
}

function extractTrendSummary(summary?: string, aiFullReport?: string): string {
  return normalizeTrendSummary(summary) || normalizeTrendSummary(aiFullReport)
}

function createEmptyGenreDistribution(): GenreDistribution {
  return { genres: {}, total: 0, snapshot_date: null }
}

function resetBaseData() {
  rankingBooks.value = []
  fanqieNewBooks.value = []
  genreDistribution.value = createEmptyGenreDistribution()
}

function resetTrendReport() {
  trendReport.value = {} as TrendReport
}

async function loadTrendReport(
  requestId: number,
  options: { forceRegenerate?: boolean; clearBeforeLoad?: boolean } = {},
) {
  const { forceRegenerate = false, clearBeforeLoad = true } = options

  if (clearBeforeLoad) {
    resetTrendReport()
  }

  isReportLoading.value = true
  const platform = currentPlatform.value
  const reportCategory = currentReportCategory.value

  try {
    const report = await TrendAPI.getTrendReport(platform, reportCategory, forceRegenerate)
    if (requestId !== loadRequestId) return
    trendReport.value = report
  } catch (error) {
    if (requestId !== loadRequestId) return
    console.error('加载趋势报告失败:', error)
    resetTrendReport()
  } finally {
    if (requestId === loadRequestId) {
      isReportLoading.value = false
    }
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// 方法
function goBack() {
  router.push('/')
}

async function selectPlatform(platformId: string) {
  currentPlatform.value = platformId
  if (platformId === 'fanqie') {
    initializeFanqieSelection()
  } else {
    const newPlatform = platforms.value.find(p => p.id === platformId)
    const categories = newPlatform?.categories || {}
    const categoryKeys = Object.keys(categories)
    currentCategory.value = categoryKeys.length > 0 ? categoryKeys[0] : 'hot'
  }
  await loadData()
}

async function selectCategory(category: string) {
  if (isFanqiePlatform.value) {
    currentFanqieCategoryId.value = category
  } else {
    currentCategory.value = category
  }
  await loadData()
}

async function selectFanqieGender(gender: string) {
  currentFanqieGender.value = gender as FanqieGenderKey
  const nextGroup = fanqieCategoryGroups.value[gender as FanqieGenderKey] || {}
  currentFanqieCategoryId.value = Object.keys(nextGroup)[0] || ''
  await loadData()
}

function initializeFanqieSelection() {
  const categoryGroups = fanqieCategoryGroups.value
  if (!categoryGroups[currentFanqieGender.value]) {
    currentFanqieGender.value = (Object.keys(categoryGroups)[0] as FanqieGenderKey) || 'male'
  }

  const currentGroup = categoryGroups[currentFanqieGender.value] || {}
  if (!currentFanqieCategoryId.value || !currentGroup[currentFanqieCategoryId.value]) {
    currentFanqieCategoryId.value = Object.keys(currentGroup)[0] || ''
  }
}

async function loadData() {
  const requestId = ++loadRequestId
  let shouldLoadReport = false

  isLoading.value = true
  isRefreshing.value = false
  isReportLoading.value = true
  resetBaseData()
  resetTrendReport()

  try {
    if (isFanqiePlatform.value) {
      initializeFanqieSelection()
      const platform = currentPlatform.value
      const readCategory = fanqieReadCategoryKey.value
      const newCategory = fanqieNewCategoryKey.value
      const [readRanking, newRanking, genres] = await Promise.all([
        TrendAPI.getRanking(platform, readCategory),
        TrendAPI.getRanking(platform, newCategory),
        TrendAPI.getGenreDistribution(platform, readCategory),
      ])
      if (requestId !== loadRequestId) return
      rankingBooks.value = readRanking.books || []
      fanqieNewBooks.value = newRanking.books || []
      genreDistribution.value = genres
      shouldLoadReport = true
    } else {
      const platform = currentPlatform.value
      const category = currentCategory.value
      const [ranking, genres] = await Promise.all([
        TrendAPI.getRanking(platform, category),
        TrendAPI.getGenreDistribution(platform, category),
      ])
      if (requestId !== loadRequestId) return
      rankingBooks.value = ranking.books || []
      fanqieNewBooks.value = []
      genreDistribution.value = genres
      shouldLoadReport = true
    }
  } catch (error) {
    if (requestId !== loadRequestId) return
    console.error('加载趋势数据失败:', error)
    resetBaseData()
    resetTrendReport()
    isReportLoading.value = false
  } finally {
    if (requestId === loadRequestId) {
      isLoading.value = false
    }
  }

  if (!shouldLoadReport || requestId !== loadRequestId) {
    return
  }

  await loadTrendReport(requestId, { clearBeforeLoad: false })
}

async function refreshData() {
  const requestId = ++loadRequestId
  let shouldLoadReport = false

  isLoading.value = true
  isRefreshing.value = true
  try {
    if (isFanqiePlatform.value) {
      initializeFanqieSelection()
      const platform = currentPlatform.value
      const readCategory = fanqieReadCategoryKey.value
      const newCategory = fanqieNewCategoryKey.value

      await Promise.all([
        TrendAPI.refreshData(platform, readCategory),
        TrendAPI.refreshData(platform, newCategory),
      ])
      const [readRanking, newRanking, genres] = await Promise.all([
        TrendAPI.getRanking(platform, readCategory),
        TrendAPI.getRanking(platform, newCategory),
        TrendAPI.getGenreDistribution(platform, readCategory),
      ])
      if (requestId !== loadRequestId) return
      rankingBooks.value = readRanking.books || []
      fanqieNewBooks.value = newRanking.books || []
      genreDistribution.value = genres
      shouldLoadReport = true
    } else {
      const platform = currentPlatform.value
      const category = currentCategory.value

      await TrendAPI.refreshData(platform, category)
      const [ranking, genres] = await Promise.all([
        TrendAPI.getRanking(platform, category),
        TrendAPI.getGenreDistribution(platform, category),
      ])
      if (requestId !== loadRequestId) return
      rankingBooks.value = ranking.books || []
      fanqieNewBooks.value = []
      genreDistribution.value = genres
      shouldLoadReport = true
    }
  } catch (error) {
    if (requestId !== loadRequestId) return
    console.error('刷新数据失败:', error)
  } finally {
    if (requestId === loadRequestId) {
      isLoading.value = false
    }
  }

  if (shouldLoadReport && requestId === loadRequestId) {
    await loadTrendReport(requestId, { forceRegenerate: true })
  } else if (requestId === loadRequestId) {
    isReportLoading.value = false
  }

  if (requestId === loadRequestId) {
    isRefreshing.value = false
  }
}

async function handleImport() {
  if (!importText.value.trim()) return
  try {
    const importCategory = isFanqiePlatform.value ? fanqieReadCategoryKey.value : currentCategory.value
    await TrendAPI.importData(currentPlatform.value, importText.value, importCategory)
    showImportModal.value = false
    importText.value = ''
    await loadData()
  } catch (error) {
    console.error('导入失败:', error)
  }
}

async function handleDeletePlatform(platform: string) {
  showDeleteMenu.value = false
  if (!confirm(`确定要删除 ${platform === 'qidian' ? '起点中文网' : '番茄小说'} 的所有趋势数据吗？此操作不可恢复。`)) {
    return
  }
  try {
    const result = await TrendAPI.deletePlatformData(platform)
    globalAlert.showSuccess(`已删除: ${result.deleted.snapshots}个快照, ${result.deleted.books}本书, ${result.deleted.reports}份报告`)
    // 如果当前平台就是要删除的平台，刷新数据
    if (currentPlatform.value === platform) {
      rankingBooks.value = []
      fanqieNewBooks.value = []
      genreDistribution.value = { genres: {}, total: 0, snapshot_date: null }
      trendReport.value = {} as TrendReport
    }
  } catch (error) {
    console.error('删除失败:', error)
    globalAlert.showError('删除失败')
  }
}

function startCreation() {
  router.push('/inspiration')
}

onMounted(async () => {
  await loadPlatforms()
  await loadData()
})

async function loadPlatforms() {
  try {
    const data = await TrendAPI.getPlatforms()
    platforms.value = data.platforms || []
    // 确保当前选中的平台在列表中
    if (platforms.value.length > 0 && !platforms.value.find(p => p.id === currentPlatform.value)) {
      currentPlatform.value = platforms.value[0].id
    }
  } catch (error) {
    console.error('加载平台数据失败:', error)
    // 降级到硬编码数据
    platforms.value = [
      { id: 'qidian', name: '起点中文网', categories: { hot: '畅销榜', monthly: '月票榜' } },
      {
        id: 'fanqie',
        name: '番茄小说',
        categories: { female_read: '女频阅读榜', male_read: '男频阅读榜' },
        meta: fanqieFallbackMeta,
      },
    ]
  }
}
</script>
