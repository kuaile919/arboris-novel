<!-- AIMETA P=文本对比查看器_高亮显示文本差异|R=文本对比_差异高亮|NR=不含内容修改|E=component:TextDiffViewer|X=internal|A=文本对比|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="text-diff-viewer">
    <!-- 视图切换 -->
    <div class="flex items-center justify-between mb-4">
      <h4 class="text-sm font-medium text-gray-700">对比视图</h4>
      <div class="flex items-center gap-3">
        <div v-if="viewMode === 'sidebyside'" class="flex items-center gap-2 text-xs text-gray-600">
          <label class="flex items-center gap-1 cursor-pointer select-none">
            <input v-model="lockMasterScroll" type="checkbox" class="cursor-pointer" />
            <span>锁定主列跟随</span>
          </label>
          <template v-if="lockMasterScroll">
            <label class="flex items-center gap-1 cursor-pointer select-none">
              <input v-model="masterScrollColumn" type="radio" value="original" class="cursor-pointer" />
              <span>原文</span>
            </label>
            <label class="flex items-center gap-1 cursor-pointer select-none">
              <input v-model="masterScrollColumn" type="radio" value="optimized" class="cursor-pointer" />
              <span>优化后</span>
            </label>
          </template>
        </div>
        <div class="flex gap-2">
        <button
          @click="viewMode = 'inline'"
          :class="[
            'px-3 py-1 text-xs rounded transition-all',
            viewMode === 'inline'
              ? 'bg-indigo-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          ]"
        >
          行内对比
        </button>
        <button
          @click="viewMode = 'sidebyside'"
          :class="[
            'px-3 py-1 text-xs rounded transition-all',
            viewMode === 'sidebyside'
              ? 'bg-indigo-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          ]"
        >
          并排对比
        </button>
        </div>
      </div>
    </div>

    <!-- 行内对比视图 -->
    <div v-if="viewMode === 'inline'" class="inline-diff-view">
      <div class="diff-content p-4 bg-gray-50 rounded-lg border border-gray-200 overflow-auto max-h-[600px]">
        <div v-html="inlineDiffHtml" class="text-sm leading-relaxed whitespace-pre-wrap"></div>
      </div>
    </div>

    <!-- 并排对比视图 -->
    <div v-else class="sidebyside-diff-view">
      <div class="grid grid-cols-2 gap-4">
        <!-- 原文 -->
        <div class="original-text">
          <div class="text-xs font-medium text-gray-500 mb-2 flex items-center gap-2">
            <span>📄</span>
            <span>原文</span>
          </div>
          <div
            ref="originalScrollEl"
            class="diff-content p-4 bg-gray-50 rounded-lg border border-gray-200 overflow-auto max-h-[600px]"
            @scroll="handleSideBySideScroll('original')"
          >
            <div v-html="originalDiffHtml" class="text-sm leading-relaxed whitespace-pre-wrap"></div>
          </div>
        </div>

        <!-- 优化后 -->
        <div class="optimized-text">
          <div class="text-xs font-medium text-gray-500 mb-2 flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span>✨</span>
              <span>优化后</span>
            </div>
            <button
              v-if="editableOptimized"
              @click="isEditingOptimized = !isEditingOptimized"
              class="px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
            >
              {{ isEditingOptimized ? '完成编辑' : '编辑' }}
            </button>
          </div>
          <div
            ref="optimizedScrollEl"
            :class="[
              'diff-content p-4 bg-gray-50 rounded-lg border border-gray-200 max-h-[600px]',
              editableOptimized && isEditingOptimized ? 'overflow-hidden' : 'overflow-auto'
            ]"
            @scroll="handleSideBySideScroll('optimized')"
          >
            <textarea
              v-if="editableOptimized && isEditingOptimized"
              ref="optimizedEditorEl"
              v-model="editedOptimizedText"
              class="optimized-editor block w-full min-h-[560px] max-h-[560px] overflow-auto bg-transparent text-sm leading-relaxed resize-none outline-none"
              @scroll="handleSideBySideScroll('optimized')"
              placeholder="可在这里人工微调优化后的内容..."
            ></textarea>
            <div v-else v-html="optimizedDiffHtml" class="text-sm leading-relaxed whitespace-pre-wrap"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 统计信息 -->
    <div class="mt-4 flex items-center gap-4 text-xs text-gray-500">
      <div class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 bg-red-200 rounded"></span>
        <span>删除: {{ stats.deleted }} 字</span>
      </div>
      <div class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 bg-green-200 rounded"></span>
        <span>新增: {{ stats.added }} 字</span>
      </div>
      <div class="flex items-center gap-1">
        <span class="inline-block w-3 h-3 bg-gray-200 rounded"></span>
        <span>未变: {{ stats.unchanged }} 字</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import DiffMatchPatch from 'diff-match-patch';

const props = defineProps({
  originalText: {
    type: String,
    required: true
  },
  optimizedText: {
    type: String,
    required: true
  },
  editableOptimized: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits<{
  (e: 'update:optimizedText', value: string): void;
}>();

const viewMode = ref<'inline' | 'sidebyside'>('inline');
const originalScrollEl = ref<HTMLElement | null>(null);
const optimizedScrollEl = ref<HTMLElement | null>(null);
const optimizedEditorEl = ref<HTMLTextAreaElement | null>(null);
const ignoreNextScrollFrom = ref<'original' | 'optimized' | null>(null);
const lockMasterScroll = ref(false);
const masterScrollColumn = ref<'original' | 'optimized'>('original');
const isEditingOptimized = ref(false);
const editedOptimizedText = ref(props.optimizedText);
const dmp = new DiffMatchPatch();

watch(
  () => props.optimizedText,
  (value) => {
    if (value !== editedOptimizedText.value) {
      editedOptimizedText.value = value;
    }
  }
);

watch(editedOptimizedText, (value) => {
  emit('update:optimizedText', value);
});

function handleSideBySideScroll(source: 'original' | 'optimized') {
  if (viewMode.value !== 'sidebyside') {
    return;
  }

  if (lockMasterScroll.value && source !== masterScrollColumn.value) {
    return;
  }

  // Ignore the scroll event triggered by our own programmatic sync.
  if (ignoreNextScrollFrom.value === source) {
    ignoreNextScrollFrom.value = null;
    return;
  }

  const sourceEl = getScrollElement(source);
  const targetEl = getScrollElement(source === 'original' ? 'optimized' : 'original');
  const targetKey = source === 'original' ? 'optimized' : 'original';

  if (!sourceEl || !targetEl) {
    return;
  }

  const sourceMax = sourceEl.scrollHeight - sourceEl.clientHeight;
  const targetMax = targetEl.scrollHeight - targetEl.clientHeight;
  const ratio = sourceMax > 0 ? sourceEl.scrollTop / sourceMax : 0;

  ignoreNextScrollFrom.value = targetKey;
  targetEl.scrollTop = targetMax > 0 ? ratio * targetMax : 0;
}

function getScrollElement(side: 'original' | 'optimized'): HTMLElement | null {
  if (side === 'original') {
    return originalScrollEl.value;
  }
  if (props.editableOptimized && isEditingOptimized.value && optimizedEditorEl.value) {
    return optimizedEditorEl.value;
  }
  return optimizedScrollEl.value;
}

// 计算 diff
const diffs = computed(() => {
  return dmp.diff_main(props.originalText, editedOptimizedText.value);
});

// 统计信息
const stats = computed(() => {
  let deleted = 0;
  let added = 0;
  let unchanged = 0;

  diffs.value.forEach(([operation, text]) => {
    const length = text.length;
    if (operation === -1) {
      deleted += length;
    } else if (operation === 1) {
      added += length;
    } else {
      unchanged += length;
    }
  });

  return { deleted, added, unchanged };
});

// 行内对比 HTML
const inlineDiffHtml = computed(() => {
  let html = '';

  diffs.value.forEach(([operation, text]) => {
    const escapedText = escapeHtml(text);

    if (operation === -1) {
      // 删除：红色背景 + 删除线
      html += `<span class="diff-deleted">${escapedText}</span>`;
    } else if (operation === 1) {
      // 新增：绿色背景
      html += `<span class="diff-added">${escapedText}</span>`;
    } else {
      // 未变
      html += escapedText;
    }
  });

  return html;
});

// 原文 diff HTML（并排视图）
const originalDiffHtml = computed(() => {
  let html = '';

  diffs.value.forEach(([operation, text]) => {
    const escapedText = escapeHtml(text);

    if (operation === -1) {
      // 删除：红色背景 + 删除线
      html += `<span class="diff-deleted">${escapedText}</span>`;
    } else if (operation === 0) {
      // 未变
      html += escapedText;
    }
    // 新增的内容不在原文中显示
  });

  return html;
});

// 优化后 diff HTML（并排视图）
const optimizedDiffHtml = computed(() => {
  let html = '';

  diffs.value.forEach(([operation, text]) => {
    const escapedText = escapeHtml(text);

    if (operation === 1) {
      // 新增：绿色背景
      html += `<span class="diff-added">${escapedText}</span>`;
    } else if (operation === 0) {
      // 未变
      html += escapedText;
    }
    // 删除的内容不在优化后显示
  });

  return html;
});

// HTML 转义
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// 优化 diff（可选，提高性能）
onMounted(() => {
  dmp.diff_cleanupSemantic(diffs.value);
});
</script>

<style scoped>
/* 删除样式 */
:deep(.diff-deleted) {
  background-color: #fee;
  text-decoration: line-through;
  color: #c33;
  padding: 2px 0;
}

/* 新增样式 */
:deep(.diff-added) {
  background-color: #dfd;
  color: #3c3;
  padding: 2px 0;
}

/* 滚动条样式 */
.diff-content::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.diff-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.diff-content::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.diff-content::-webkit-scrollbar-thumb:hover {
  background: #a1a1a1;
}
</style>
