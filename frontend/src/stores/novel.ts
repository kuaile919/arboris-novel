// AIMETA P=小说状态_当前小说数据管理|R=currentNovel_chapters_fetch|NR=不含API调用|E=store:novel|X=internal|A=useNovelStore|D=pinia|S=none|RD=./README.ai
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { NovelProject, NovelProjectSummary, ConverseResponse, BlueprintGenerationResponse, Blueprint, DeleteNovelsResponse, ChapterOutline, OutlinePreviewResponse } from '@/api/novel'
import { NovelAPI } from '@/api/novel'

type ChapterGenerationNoticeStatus = 'successful' | 'waiting_for_confirm' | 'failed' | 'evaluation_failed'

interface ChapterGenerationFinishedDetail {
  projectId: string
  projectTitle: string
  chapterNumber: number
  status: ChapterGenerationNoticeStatus
}

export const useNovelStore = defineStore('novel', () => {
  // State
  const projects = ref<NovelProjectSummary[]>([])
  const currentProject = ref<NovelProject | null>(null)
  const currentConversationState = ref<any>({})
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const pendingChapterEdits = new Map<string, string>()
  const outlinePreview = ref<OutlinePreviewResponse | null>(null)
  const isPreviewLoading = ref(false)
  let loadProjectRequestSeq = 0
  const chapterStatusTrackers = new Map<string, number>()
  const chapterNoticeDedup = new Set<string>()

  const notifyChapterGenerationFinished = (detail: ChapterGenerationFinishedDetail) => {
    if (typeof window === 'undefined') {
      return
    }
    const dedupKey = `${detail.projectId}:${detail.chapterNumber}:${detail.status}`
    if (chapterNoticeDedup.has(dedupKey)) {
      return
    }
    chapterNoticeDedup.add(dedupKey)
    window.dispatchEvent(
      new CustomEvent<ChapterGenerationFinishedDetail>('chapter-generation-finished', { detail })
    )
  }

  const stopChapterStatusTracking = (projectId: string, chapterNumber: number) => {
    const trackerKey = `${projectId}:${chapterNumber}`
    const timer = chapterStatusTrackers.get(trackerKey)
    if (timer !== undefined) {
      window.clearInterval(timer)
      chapterStatusTrackers.delete(trackerKey)
    }
  }

  const startChapterStatusTracking = (projectId: string, chapterNumber: number, projectTitle: string) => {
    if (typeof window === 'undefined') {
      return
    }
    stopChapterStatusTracking(projectId, chapterNumber)

    const trackerKey = `${projectId}:${chapterNumber}`
    const timer = window.setInterval(async () => {
      try {
        const status = await NovelAPI.getChapterRuntimeStatus(projectId, chapterNumber)
        if (status.generation_status === 'generating' || status.generation_status === 'evaluating' || status.generation_status === 'selecting') {
          return
        }

        stopChapterStatusTracking(projectId, chapterNumber)

        if (
          status.generation_status === 'successful' ||
          status.generation_status === 'waiting_for_confirm' ||
          status.generation_status === 'failed' ||
          status.generation_status === 'evaluation_failed'
        ) {
          notifyChapterGenerationFinished({
            projectId,
            projectTitle,
            chapterNumber,
            status: status.generation_status,
          })
        }
      } catch {
        // 静默重试，避免后台跟踪打断用户
      }
    }, 5000)

    chapterStatusTrackers.set(trackerKey, timer)
  }

  // Getters
  const projectsCount = computed(() => projects.value.length)
  const hasCurrentProject = computed(() => currentProject.value !== null)

  // Actions
  async function loadProjects() {
    isLoading.value = true
    error.value = null
    try {
      projects.value = await NovelAPI.getAllNovels()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载项目失败'
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(title: string, initialPrompt: string) {
    isLoading.value = true
    error.value = null
    try {
      const project = await NovelAPI.createNovel(title, initialPrompt)
      currentProject.value = project
      currentConversationState.value = {}
      return project
    } catch (err) {
      error.value = err instanceof Error ? err.message : '创建项目失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function loadProject(projectId: string, silent: boolean = false) {
    const requestSeq = ++loadProjectRequestSeq
    if (!silent) {
      isLoading.value = true
    }
    error.value = null
    try {
      const project = await NovelAPI.getNovel(projectId)
      if (requestSeq !== loadProjectRequestSeq) {
        return
      }
      currentProject.value = project
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载项目失败'
    } finally {
      if (!silent) {
        isLoading.value = false
      }
    }
  }

  async function loadChapter(chapterNumber: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const chapter = await NovelAPI.getChapter(currentProject.value.id, chapterNumber)
      const project = currentProject.value
      if (!Array.isArray(project.chapters)) {
        project.chapters = []
      }
      const index = project.chapters.findIndex(ch => ch.chapter_number === chapterNumber)
      if (index >= 0) {
        project.chapters.splice(index, 1, chapter)
      } else {
        project.chapters.push(chapter)
      }
      project.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
      return chapter
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载章节失败'
      throw err
    }
  }

  async function sendConversation(userInput: any): Promise<ConverseResponse> {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const response = await NovelAPI.converseConcept(
        currentProject.value.id,
        userInput,
        currentConversationState.value
      )
      currentConversationState.value = response.conversation_state
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '对话失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateBlueprint(): Promise<BlueprintGenerationResponse> {
    // Generate blueprint from conversation history
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      return await NovelAPI.generateBlueprint(currentProject.value.id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成蓝图失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function saveBlueprint(blueprint: Blueprint) {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      if (!blueprint) {
        throw new Error('缺少蓝图数据')
      }
      const updatedProject = await NovelAPI.saveBlueprint(projectId, blueprint)
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '保存蓝图失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateChapter(chapterNumber: number): Promise<NovelProject> {
    // 注意：这里不设置全局 isLoading，因为 WritingDesk.vue 有自己的局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const projectTitle = currentProject.value.title || '未命名小说'
      startChapterStatusTracking(projectId, chapterNumber, projectTitle)
      const updatedProject = await NovelAPI.generateChapter(projectId, chapterNumber)
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject // 更新 store 中的当前项目
      }
      const chapter = updatedProject.chapters?.find(ch => ch.chapter_number === chapterNumber)
      if (
        chapter &&
        (
          chapter.generation_status === 'successful' ||
          chapter.generation_status === 'waiting_for_confirm' ||
          chapter.generation_status === 'failed' ||
          chapter.generation_status === 'evaluation_failed'
        )
      ) {
        stopChapterStatusTracking(projectId, chapterNumber)
        notifyChapterGenerationFinished({
          projectId,
          projectTitle,
          chapterNumber,
          status: chapter.generation_status,
        })
      }
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成章节失败'
      throw err
    }
  }

  async function evaluateChapter(chapterNumber: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const updatedProject = await NovelAPI.evaluateChapter(projectId, chapterNumber)
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject
      }
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '评估章节失败'
      throw err
    }
  }

  async function selectChapterVersion(chapterNumber: number, versionIndex: number) {
    // 不设置全局 isLoading，让调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const updatedProject = await NovelAPI.selectChapterVersion(
        projectId,
        chapterNumber,
        versionIndex
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject // 更新 store
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '选择章节版本失败'
      throw err
    }
  }

  async function deleteProjects(projectIds: string[]): Promise<DeleteNovelsResponse> {
    isLoading.value = true
    error.value = null
    try {
      const response = await NovelAPI.deleteNovels(projectIds)
      
      // 从本地项目列表中移除已删除的项目
      projects.value = projects.value.filter(project => !projectIds.includes(project.id))
      
      // 如果当前项目被删除，清空当前项目
      if (currentProject.value && projectIds.includes(currentProject.value.id)) {
        currentProject.value = null
        currentConversationState.value = {}
      }
      
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除项目失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateChapterOutline(chapterOutline: ChapterOutline) {
    // 不设置全局 isLoading，让调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const updatedProject = await NovelAPI.updateChapterOutline(
        projectId,
        chapterOutline
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject // 更新 store
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '更新章节大纲失败'
      throw err
    }
  }

  async function deleteChapter(chapterNumbers: number | number[]) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
      const updatedProject = await NovelAPI.deleteChapter(
        projectId,
        numbersToDelete
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject // 更新 store
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除章节失败'
      throw err
    }
  }

  async function generateChapterOutline(startChapter: number, numChapters: number, userHint?: string) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      const updatedProject = await NovelAPI.generateChapterOutline(
        projectId,
        startChapter,
        numChapters,
        userHint
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject // 更新 store
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '生成大纲失败'
      throw err
    }
  }

  async function previewChapterOutline(startChapter: number, numChapters: number, userHint?: string, totalChapters?: number) {
    isPreviewLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const preview = await NovelAPI.previewChapterOutline(
        currentProject.value.id,
        startChapter,
        numChapters,
        userHint,
        totalChapters
      )
      outlinePreview.value = preview
      return preview
    } catch (err) {
      error.value = err instanceof Error ? err.message : '预览大纲失败'
      throw err
    } finally {
      isPreviewLoading.value = false
    }
  }

  async function confirmChapterOutline(startChapter: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('没有当前项目')
      }
      const projectId = currentProject.value.id
      if (!outlinePreview.value) {
        throw new Error('没有预览数据')
      }
      const updatedProject = await NovelAPI.confirmChapterOutline(
        projectId,
        startChapter,
        outlinePreview.value as unknown as Record<string, any>
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject
      }
      outlinePreview.value = null // 清除预览
      // 触发伏笔数据更新事件
      window.dispatchEvent(new CustomEvent('foreshadowing-updated'))
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '确认大纲失败'
      throw err
    }
  }

  function clearOutlinePreview() {
    outlinePreview.value = null
  }

  async function editChapterContent(projectId: string, chapterNumber: number, content: string) {
    error.value = null
    const requestKey = `${projectId}:${chapterNumber}`
    pendingChapterEdits.set(requestKey, content)
    const project = currentProject.value
    let previousContent: string | null = null
    let previousWordCount: number | undefined
    let versionIndex = -1
    if (project) {
      const chapter = project.chapters.find(ch => ch.chapter_number === chapterNumber)
      if (chapter) {
        previousContent = chapter.content ?? null
        previousWordCount = chapter.word_count
        chapter.content = content
        chapter.generation_status = 'successful'
        chapter.word_count = content.length
        if (Array.isArray(chapter.versions) && previousContent !== null) {
          versionIndex = chapter.versions.findIndex(v => v === previousContent)
          if (versionIndex >= 0) {
            chapter.versions.splice(versionIndex, 1, content)
          }
        }
      }
    }
    try {
      const updatedChapter = await NovelAPI.editChapterContent(projectId, chapterNumber, content)
      if (pendingChapterEdits.get(requestKey) !== content) {
        return
      }
      if (project) {
        const chapters = project.chapters
        const index = chapters.findIndex(ch => ch.chapter_number === chapterNumber)
        if (index >= 0) {
          chapters.splice(index, 1, updatedChapter)
        } else {
          chapters.push(updatedChapter)
          chapters.sort((a, b) => a.chapter_number - b.chapter_number)
        }
      }
      pendingChapterEdits.delete(requestKey)
    } catch (err) {
      if (pendingChapterEdits.get(requestKey) === content) {
        pendingChapterEdits.delete(requestKey)
        if (project) {
          const chapter = project.chapters.find(ch => ch.chapter_number === chapterNumber)
          if (chapter) {
            chapter.content = previousContent
            chapter.word_count = previousWordCount
            if (Array.isArray(chapter.versions) && versionIndex >= 0 && previousContent !== null) {
              chapter.versions.splice(versionIndex, 1, previousContent)
            }
          }
        }
      }
      error.value = err instanceof Error ? err.message : '编辑章节内容失败'
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  function setCurrentProject(project: NovelProject | null) {
    currentProject.value = project
  }

  return {
    // State
    projects,
    currentProject,
    currentConversationState,
    isLoading,
    error,
    outlinePreview,
    isPreviewLoading,
    // Getters
    projectsCount,
    hasCurrentProject,
    // Actions
    loadProjects,
    createProject,
    loadProject,
    loadChapter,
    sendConversation,
    generateBlueprint,
    saveBlueprint,
    generateChapter,
    evaluateChapter,
    selectChapterVersion,
    deleteProjects,
    updateChapterOutline,
    deleteChapter,
    generateChapterOutline,
    previewChapterOutline,
    confirmChapterOutline,
    clearOutlinePreview,
    editChapterContent,
    clearError,
    setCurrentProject
  }
})
