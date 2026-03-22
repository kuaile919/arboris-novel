<template>
  <div class="reference-library">
    <div class="toolbar">
      <div class="hint">
        上传原著（`txt/md/epub`）后会自动向量化，写作时可被 RAG 检索。
      </div>
      <label class="upload-btn" :class="{ disabled: uploading }">
        <input
          type="file"
          :disabled="uploading"
          accept=".txt,.md,.markdown,.epub"
          @change="onPickFile"
        >
        {{ uploading ? '上传中...' : '上传参考书' }}
      </label>
    </div>

    <p v-if="message" class="message success">{{ message }}</p>
    <p v-if="error" class="message error">{{ error }}</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="documents.length === 0" class="empty">
      暂无参考文档。建议先上传原著正文或设定集，再开始写作。
    </div>

    <div v-else class="list">
      <article v-for="doc in documents" :key="doc.id" class="item">
        <div class="meta">
          <h4>{{ doc.title }}</h4>
          <p>
            {{ doc.filename }} · {{ formatSize(doc.file_size) }} · {{ doc.char_count }}字 ·
            {{ doc.chunk_count }}片段
          </p>
          <p class="subline">状态：{{ statusLabel(doc.status) }} · 上传于 {{ formatDateTime(doc.created_at) }}</p>
          <p v-if="doc.error_message" class="errline">{{ doc.error_message }}</p>
        </div>
        <button class="delete-btn" :disabled="deletingId === doc.id" @click="remove(doc.id)">
          {{ deletingId === doc.id ? '删除中...' : '删除' }}
        </button>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NovelAPI, type ReferenceDocumentItem } from '@/api/novel'
import { formatDateTime } from '@/utils/date'

const props = defineProps<{
  projectId: string
}>()

const documents = ref<ReferenceDocumentItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref<number | null>(null)
const error = ref('')
const message = ref('')

const load = async () => {
  if (!props.projectId) return
  loading.value = true
  error.value = ''
  try {
    documents.value = await NovelAPI.listReferenceDocuments(props.projectId)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

const onPickFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await NovelAPI.uploadReferenceDocument(props.projectId, file)
    message.value = `${result.document.title} 已完成向量化`
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上传失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

const remove = async (id: number) => {
  deletingId.value = id
  error.value = ''
  message.value = ''
  try {
    await NovelAPI.deleteReferenceDocument(props.projectId, id)
    documents.value = documents.value.filter((doc) => doc.id !== id)
    message.value = '已删除参考文档'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  } finally {
    deletingId.value = null
  }
}

const statusLabel = (status: string) => {
  if (status === 'ready') return '已就绪'
  if (status === 'processing') return '处理中'
  if (status === 'failed') return '失败'
  return status
}

const formatSize = (size: number) => {
  if (size < 1024) return `${size}B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`
  return `${(size / (1024 * 1024)).toFixed(2)}MB`
}

onMounted(load)
</script>

<style scoped>
.reference-library {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.hint {
  color: var(--md-on-surface-variant);
  font-size: 13px;
}

.upload-btn {
  cursor: pointer;
  background: var(--md-primary);
  color: var(--md-on-primary);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 13px;
}

.upload-btn.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.upload-btn input {
  display: none;
}

.message {
  margin: 0;
  font-size: 13px;
}

.message.success {
  color: #2e7d32;
}

.message.error {
  color: #c62828;
}

.loading,
.empty {
  color: var(--md-on-surface-variant);
  font-size: 14px;
  padding: 12px 0;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.item {
  border: 1px solid var(--md-outline-variant);
  border-radius: 14px;
  padding: 12px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.meta h4 {
  margin: 0 0 4px;
  font-size: 15px;
  color: var(--md-on-surface);
}

.meta p {
  margin: 0;
  font-size: 12px;
  color: var(--md-on-surface-variant);
}

.subline {
  margin-top: 4px !important;
}

.errline {
  margin-top: 6px !important;
  color: #c62828 !important;
}

.delete-btn {
  border: 1px solid var(--md-outline);
  color: var(--md-on-surface);
  border-radius: 999px;
  background: transparent;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.delete-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
