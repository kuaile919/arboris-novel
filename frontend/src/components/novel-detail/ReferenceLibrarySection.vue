<template>
  <div class="ima-library">
    <div class="toolbar">
      <div class="toolbar-copy">
        <h3>连接 IMA 知识库</h3>
        <p>选择知识库后即可浏览文件夹、搜索内容、上传文件和导入网页。</p>
      </div>
      <div class="toolbar-actions">
        <div class="kb-search">
          <input
            v-model.trim="knowledgeBaseQuery"
            type="text"
            class="text-input"
            placeholder="按名称搜索知识库"
            @keyup.enter="loadKnowledgeBases"
          >
          <button class="secondary-btn" :disabled="loadingKnowledgeBases" @click="loadKnowledgeBases">
            {{ loadingKnowledgeBases ? '加载中...' : '刷新列表' }}
          </button>
        </div>
        <select v-model="selectedKnowledgeBaseId" class="select-input" :disabled="loadingKnowledgeBases">
          <option value="">请选择知识库</option>
          <option v-for="item in knowledgeBases" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
      </div>
    </div>

    <p v-if="message" class="message success">{{ message }}</p>
    <p v-if="error" class="message error">{{ error }}</p>

    <div v-if="selectedKnowledgeBase" class="kb-card">
      <div>
        <h4>{{ selectedKnowledgeBase.name }}</h4>
        <p v-if="selectedKnowledgeBase.description">{{ selectedKnowledgeBase.description }}</p>
        <p v-else class="muted">这个知识库暂时没有填写描述。</p>
      </div>
      <div class="kb-meta">
        <span v-if="selectedKnowledgeBase.creator">创建者：{{ selectedKnowledgeBase.creator }}</span>
        <span v-if="selectedKnowledgeBase.role_type">身份：{{ selectedKnowledgeBase.role_type }}</span>
        <span v-if="selectedKnowledgeBase.content_count !== null && selectedKnowledgeBase.content_count !== undefined">
          内容数：{{ selectedKnowledgeBase.content_count }}
        </span>
      </div>
      <div
        v-if="selectedKnowledgeBase.recommended_questions && selectedKnowledgeBase.recommended_questions.length"
        class="questions"
      >
        <span v-for="question in selectedKnowledgeBase.recommended_questions" :key="question" class="question-chip">
          {{ question }}
        </span>
      </div>
    </div>

    <div v-if="!selectedKnowledgeBase" class="empty">
      先从上方选择一个 IMA 知识库，再开始浏览或上传资料。
    </div>

    <template v-else>
      <div class="actions-panel">
        <div class="search-box">
          <input
            v-model.trim="searchQuery"
            type="text"
            class="text-input"
            placeholder="在当前知识库中搜索，未命中时自动降级到联网搜索"
            @keyup.enter="handleSearchSubmit"
          >
          <button class="secondary-btn" :disabled="loadingItems" @click="handleSearchSubmit">
            {{ searchActive ? '重新搜索' : '搜索' }}
          </button>
          <button v-if="searchActive" class="ghost-btn" @click="clearSearch">返回浏览</button>
        </div>

        <div class="upload-row">
          <label class="primary-btn" :class="{ disabled: uploading }">
            <input
              type="file"
              :disabled="uploading"
              accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.xmind"
              @change="onPickFile"
            >
            {{ uploading ? '上传中...' : '上传文件' }}
          </label>
          <span class="muted">支持文档、表格、Markdown、图片、Xmind；当前版本不支持音视频。</span>
        </div>

        <div class="url-import">
          <textarea
            v-model="urlInput"
            class="text-area"
            rows="3"
            placeholder="每行一个网页 URL，支持普通网页和微信公众号文章"
          ></textarea>
          <button class="secondary-btn" :disabled="importingUrls" @click="submitUrls">
            {{ importingUrls ? '导入中...' : '导入网页' }}
          </button>
        </div>
      </div>

      <div v-if="!searchActive" class="breadcrumbs">
        <button
          v-for="entry in currentPath"
          :key="entry.id || entry.name"
          class="breadcrumb"
          @click="openBreadcrumb(entry)"
        >
          {{ entry.name }}
        </button>
      </div>

      <div v-if="loadingItems" class="loading">加载中...</div>
      <div v-else-if="searchActive && searchFallbackUsed && searchFallbackResults.length" class="fallback-panel">
        <div class="fallback-header">
          <h4>{{ searchFallbackProvider || '搜索降级结果' }}</h4>
          <p>{{ searchFallbackMessage || 'IMA 未命中，已切换到联网搜索。' }}</p>
        </div>
        <div class="list">
          <article v-for="item in searchFallbackResults" :key="item.link" class="item fallback-item">
            <div class="item-icon">🌐</div>
            <div class="item-body">
              <div class="item-title-row">
                <h4>{{ item.title }}</h4>
                <span v-if="item.date" class="item-tags">{{ item.date }}</span>
              </div>
              <p v-if="item.snippet" class="highlight">{{ item.snippet }}</p>
              <a class="fallback-link" :href="item.link" target="_blank" rel="noreferrer">
                {{ item.link }}
              </a>
            </div>
          </article>
        </div>
      </div>
      <div v-else-if="visibleItems.length === 0" class="empty">
        {{ searchActive ? '没有搜索到匹配内容。' : '当前目录暂无内容。' }}
      </div>

      <div v-else class="list">
        <article
          v-for="item in visibleItems"
          :key="item.id"
          class="item"
          :class="{ clickable: item.is_folder }"
          @click="item.is_folder && openFolder(item)"
        >
          <div class="item-icon">{{ item.is_folder ? '📁' : '📄' }}</div>
          <div class="item-body">
            <div class="item-title-row">
              <h4>{{ item.title }}</h4>
              <span v-if="item.tags.length" class="item-tags">{{ item.tags.join(' / ') }}</span>
            </div>
            <p v-if="item.highlight_content" class="highlight">{{ item.highlight_content }}</p>
            <p v-else class="muted">{{ item.is_folder ? '点击进入文件夹' : '文件条目' }}</p>
          </div>
        </article>
      </div>

      <button
        v-if="showLoadMore"
        class="secondary-btn load-more"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? '加载中...' : '加载更多' }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  APIError,
  NovelAPI,
  type IMAKnowledgeBase,
  type IMAFallbackSearchResult,
  type IMAKnowledgeItem,
  type IMAKnowledgePathEntry
} from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'

const props = defineProps<{
  projectId: string
}>()

const knowledgeBases = ref<IMAKnowledgeBase[]>([])
const knowledgeBaseQuery = ref('')
const selectedKnowledgeBaseId = ref('')
const selectedKnowledgeBase = ref<IMAKnowledgeBase | null>(null)

const browsingItems = ref<IMAKnowledgeItem[]>([])
const currentPath = ref<IMAKnowledgePathEntry[]>([])
const currentFolderId = ref<string | null>(null)
const nextCursor = ref('')
const isEnd = ref(true)

const searchQuery = ref('')
const searchActive = ref(false)
const searchItems = ref<IMAKnowledgeItem[]>([])
const searchNextCursor = ref('')
const searchIsEnd = ref(true)
const searchFallbackUsed = ref(false)
const searchFallbackProvider = ref('')
const searchFallbackMessage = ref('')
const searchFallbackResults = ref<IMAFallbackSearchResult[]>([])

const urlInput = ref('')
const loadingKnowledgeBases = ref(false)
const loadingItems = ref(false)
const loadingMore = ref(false)
const uploading = ref(false)
const importingUrls = ref(false)
const message = ref('')
const error = ref('')

const visibleItems = computed(() => (searchActive.value ? searchItems.value : browsingItems.value))
const showLoadMore = computed(() =>
  searchActive.value
    ? !searchFallbackUsed.value && !searchIsEnd.value && searchItems.value.length > 0
    : !isEnd.value && browsingItems.value.length > 0
)

const clearFeedback = () => {
  message.value = ''
  error.value = ''
}

const dedupeItems = (items: IMAKnowledgeItem[]) => {
  const map = new Map<string, IMAKnowledgeItem>()
  items.forEach((item) => map.set(item.id, item))
  return Array.from(map.values())
}

const loadKnowledgeBases = async () => {
  if (!props.projectId) return
  loadingKnowledgeBases.value = true
  clearFeedback()
  try {
    const response = knowledgeBaseQuery.value
      ? await NovelAPI.searchIMAKnowledgeBases(props.projectId, knowledgeBaseQuery.value)
      : await NovelAPI.getIMAAddableKnowledgeBases(props.projectId)
    knowledgeBases.value = response.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载知识库失败'
  } finally {
    loadingKnowledgeBases.value = false
  }
}

const loadKnowledgeBaseDetail = async (knowledgeBaseId: string) => {
  const response = await NovelAPI.getIMAKnowledgeBase(props.projectId, knowledgeBaseId)
  selectedKnowledgeBase.value = response.knowledge_base
}

const loadItems = async (options: { reset?: boolean; folderId?: string | null; cursor?: string } = {}) => {
  if (!selectedKnowledgeBaseId.value) return
  const reset = options.reset ?? true
  if (reset) {
    loadingItems.value = true
  } else {
    loadingMore.value = true
  }
  clearFeedback()
  try {
    const response = await NovelAPI.listIMAKnowledgeItems(props.projectId, selectedKnowledgeBaseId.value, {
      folderId: options.folderId ?? currentFolderId.value,
      cursor: options.cursor ?? '',
      limit: 20
    })
    currentFolderId.value = options.folderId ?? currentFolderId.value
    currentPath.value = response.current_path
    nextCursor.value = response.next_cursor
    isEnd.value = response.is_end
    browsingItems.value = reset ? response.items : dedupeItems([...browsingItems.value, ...response.items])
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载知识库内容失败'
  } finally {
    loadingItems.value = false
    loadingMore.value = false
  }
}

const runSearch = async (cursor = '', append = false) => {
  if (!selectedKnowledgeBaseId.value) {
    error.value = '请先选择知识库'
    return
  }
  if (!searchQuery.value.trim()) {
    clearSearch()
    return
  }
  if (!append) {
    loadingItems.value = true
  } else {
    loadingMore.value = true
  }
  clearFeedback()
  try {
    const response = await NovelAPI.searchIMAKnowledgeItems(
      props.projectId,
      selectedKnowledgeBaseId.value,
      searchQuery.value.trim(),
      cursor
    )
    searchActive.value = true
    searchNextCursor.value = response.next_cursor
    searchIsEnd.value = response.is_end
    searchItems.value = append ? dedupeItems([...searchItems.value, ...response.items]) : response.items
    searchFallbackUsed.value = Boolean(response.fallback_used)
    searchFallbackProvider.value = response.fallback_provider || ''
    searchFallbackMessage.value = response.fallback_message || ''
    searchFallbackResults.value = response.fallback_results || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : '搜索失败'
  } finally {
    loadingItems.value = false
    loadingMore.value = false
  }
}

const handleSearchSubmit = async () => {
  await runSearch()
}

const clearSearch = () => {
  searchActive.value = false
  searchItems.value = []
  searchNextCursor.value = ''
  searchIsEnd.value = true
  searchFallbackUsed.value = false
  searchFallbackProvider.value = ''
  searchFallbackMessage.value = ''
  searchFallbackResults.value = []
}

const openFolder = async (item: IMAKnowledgeItem) => {
  if (!item.is_folder) return
  clearSearch()
  await loadItems({ reset: true, folderId: item.id })
}

const openBreadcrumb = async (entry: IMAKnowledgePathEntry) => {
  clearSearch()
  await loadItems({ reset: true, folderId: entry.is_root ? null : entry.id })
}

const reloadCurrentView = async () => {
  if (searchActive.value && searchQuery.value.trim()) {
    await runSearch()
    return
  }
  await loadItems({ reset: true, folderId: currentFolderId.value })
}

const performUpload = async (file: File, onDuplicate: 'error' | 'rename' = 'error') => {
  if (!selectedKnowledgeBaseId.value) {
    error.value = '请先选择知识库'
    return
  }
  uploading.value = true
  clearFeedback()
  try {
    const result = await NovelAPI.uploadIMAKnowledgeFile(props.projectId, selectedKnowledgeBaseId.value, file, {
      folderId: currentFolderId.value,
      onDuplicate
    })
    message.value =
      result.duplicate_handling === 'renamed'
        ? `${result.original_name} 已按 ${result.final_name} 上传到「${result.knowledge_base.name}」`
        : `${result.final_name} 已添加到「${result.knowledge_base.name}」`
    await reloadCurrentView()
  } catch (e) {
    if (e instanceof APIError && e.status === 409 && e.data?.error_code === 'duplicate_name') {
      const confirmed = await globalAlert.showConfirm(
        `${e.data.duplicate_name} 已存在，是否保留两者并改名为 ${e.data.suggested_name} 后继续上传？`,
        '发现同名文件'
      )
      if (confirmed) {
        await performUpload(file, 'rename')
        return
      }
      message.value = '已取消上传'
      return
    }
    error.value = e instanceof Error ? e.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

const onPickFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await performUpload(file)
  input.value = ''
}

const submitUrls = async () => {
  if (!selectedKnowledgeBaseId.value) {
    error.value = '请先选择知识库'
    return
  }
  const urls = urlInput.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (!urls.length) {
    error.value = '请至少输入一个网页 URL'
    return
  }

  importingUrls.value = true
  clearFeedback()
  try {
    const result = await NovelAPI.importIMAUrls(
      props.projectId,
      selectedKnowledgeBaseId.value,
      urls,
      currentFolderId.value
    )
    message.value = result.message
    urlInput.value = ''
    await reloadCurrentView()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '导入网页失败'
  } finally {
    importingUrls.value = false
  }
}

const loadMore = async () => {
  if (searchActive.value) {
    await runSearch(searchNextCursor.value, true)
    return
  }
  await loadItems({ reset: false, folderId: currentFolderId.value, cursor: nextCursor.value })
}

watch(
  () => selectedKnowledgeBaseId.value,
  async (knowledgeBaseId) => {
    if (!knowledgeBaseId) {
      selectedKnowledgeBase.value = null
      browsingItems.value = []
      currentPath.value = []
      currentFolderId.value = null
      clearSearch()
      return
    }

    clearFeedback()
    clearSearch()
    currentFolderId.value = null
    try {
      await loadKnowledgeBaseDetail(knowledgeBaseId)
      await loadItems({ reset: true, folderId: null })
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载知识库失败'
    }
  }
)

onMounted(loadKnowledgeBases)
</script>

<style scoped>
.ima-library {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.toolbar,
.actions-panel,
.kb-card {
  border: 1px solid var(--md-outline-variant);
  border-radius: 18px;
  padding: 16px;
  background: var(--md-surface-container-lowest);
}

.toolbar {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  flex-wrap: wrap;
}

.toolbar-copy h3,
.kb-card h4 {
  margin: 0 0 6px;
  color: var(--md-on-surface);
}

.toolbar-copy p,
.kb-card p,
.muted,
.highlight {
  margin: 0;
  color: var(--md-on-surface-variant);
  font-size: 13px;
}

.toolbar-actions,
.kb-search,
.search-box,
.upload-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-actions {
  min-width: min(100%, 420px);
  flex-direction: column;
  align-items: stretch;
}

.text-input,
.select-input,
.text-area {
  width: 100%;
  border: 1px solid var(--md-outline);
  border-radius: 12px;
  background: var(--md-surface);
  color: var(--md-on-surface);
  padding: 10px 12px;
  font-size: 14px;
}

.text-area {
  resize: vertical;
}

.primary-btn,
.secondary-btn,
.ghost-btn,
.breadcrumb {
  border: none;
  border-radius: 999px;
  padding: 9px 14px;
  font-size: 13px;
  cursor: pointer;
}

.primary-btn {
  background: var(--md-primary);
  color: var(--md-on-primary);
}

.secondary-btn {
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}

.ghost-btn,
.breadcrumb {
  background: transparent;
  color: var(--md-primary);
  border: 1px solid var(--md-outline-variant);
}

.primary-btn.disabled,
.secondary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.primary-btn input {
  display: none;
}

.kb-meta,
.questions,
.breadcrumbs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.kb-meta span,
.question-chip {
  font-size: 12px;
  border-radius: 999px;
  padding: 4px 10px;
  background: var(--md-surface-container-high);
  color: var(--md-on-surface-variant);
}

.actions-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.url-import {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.url-import .text-area {
  flex: 1;
}

.message {
  margin: 0;
  font-size: 13px;
}

.success {
  color: #2e7d32;
}

.error {
  color: #c62828;
}

.empty,
.loading {
  padding: 18px 0;
  color: var(--md-on-surface-variant);
  font-size: 14px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fallback-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fallback-header h4 {
  margin: 0 0 4px;
  color: var(--md-on-surface);
}

.fallback-header p {
  margin: 0;
  color: var(--md-on-surface-variant);
  font-size: 13px;
}

.item {
  display: flex;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--md-outline-variant);
  border-radius: 16px;
  background: var(--md-surface);
}

.item.clickable {
  cursor: pointer;
}

.item-icon {
  width: 32px;
  font-size: 20px;
  line-height: 1.4;
}

.item-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-title-row {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  align-items: flex-start;
}

.item-title-row h4 {
  margin: 0;
  color: var(--md-on-surface);
  font-size: 15px;
}

.item-tags {
  font-size: 12px;
  color: var(--md-primary);
}

.highlight {
  color: var(--md-on-surface);
}

.fallback-link {
  color: var(--md-primary);
  font-size: 12px;
  text-decoration: none;
  word-break: break-all;
}

.fallback-link:hover {
  text-decoration: underline;
}

.load-more {
  align-self: flex-start;
}

@media (max-width: 768px) {
  .url-import {
    flex-direction: column;
  }

  .secondary-btn,
  .primary-btn,
  .ghost-btn {
    width: 100%;
    text-align: center;
  }
}
</style>
