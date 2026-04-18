<!-- AIMETA P=根组件_应用根节点|R=全局布局_RouterView|NR=不含页面逻辑|E=component:App|X=ui|A=RouterView|D=vue-router|S=dom|RD=./README.ai -->
<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import { NMessageProvider } from 'naive-ui'
import router from '@/router'
import CustomAlert from '@/components/CustomAlert.vue'
import { globalAlert } from '@/composables/useAlert'

type ChapterGenerationNoticeStatus = 'successful' | 'waiting_for_confirm' | 'failed' | 'evaluation_failed'

interface ChapterGenerationFinishedDetail {
  projectId: string
  projectTitle: string
  chapterNumber: number
  status: ChapterGenerationNoticeStatus
}

const getChapterNoticeMessage = (detail: ChapterGenerationFinishedDetail): string => {
  if (detail.status === 'failed' || detail.status === 'evaluation_failed') {
    return `《${detail.projectTitle}》第${detail.chapterNumber}章生成失败`
  }
  return `《${detail.projectTitle}》第${detail.chapterNumber}章已生成完成`
}

const handleChapterGenerationFinished = async (event: Event) => {
  const customEvent = event as CustomEvent<ChapterGenerationFinishedDetail>
  const detail = customEvent.detail
  if (!detail?.projectId || !detail.chapterNumber) {
    return
  }

  const shouldNavigate = await globalAlert.showAlert(
    getChapterNoticeMessage(detail),
    'confirmation',
    '章节更新提醒',
    {
      showCancel: true,
      confirmText: '前往查看',
      cancelText: '稍后',
    }
  )

  if (!shouldNavigate) {
    return
  }

  await router.push({
    name: 'writing-desk',
    params: { id: detail.projectId },
    query: { chapter: String(detail.chapterNumber) },
  })
}

onMounted(() => {
  window.addEventListener('chapter-generation-finished', handleChapterGenerationFinished as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('chapter-generation-finished', handleChapterGenerationFinished as EventListener)
})
</script>

<template>
  <n-message-provider>
    <div>
      <RouterView />

      <!-- 全局提示框 -->
      <CustomAlert
        v-for="alert in globalAlert.alerts.value"
        :key="alert.id"
        :visible="alert.visible"
        :type="alert.type"
        :title="alert.title"
        :message="alert.message"
        :show-cancel="alert.showCancel"
        :confirm-text="alert.confirmText"
        :cancel-text="alert.cancelText"
        @confirm="globalAlert.closeAlert(alert.id, true)"
        @cancel="globalAlert.closeAlert(alert.id, false)"
        @close="globalAlert.closeAlert(alert.id, false)"
      />
    </div>
  </n-message-provider>
</template>

<style scoped>
</style>
