// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// API 配置
// 在生产环境中使用相对路径，在开发环境中使用绝对路径
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'

// 统一的请求处理函数
const request = async (url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  // 如果 body 是 FormData，删除 Content-Type header，让浏览器自动设置（包含 boundary）
  if (options.body instanceof FormData) {
    headers.delete('Content-Type')
  }

  if (authStore.isAuthenticated && authStore.token) {
    headers.set('Authorization', `Bearer ${authStore.token}`)
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401) {
    // Token 失效或未授权
    authStore.logout()
    router.push('/login')
    throw new Error('会话已过期，请重新登录')
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `请求失败，状态码: ${response.status}`)
  }

  return response.json()
}

// 类型定义
export interface NovelProject {
  id: string
  title: string
  initial_prompt: string
  blueprint?: Blueprint
  chapters: Chapter[]
  conversation_history: ConversationMessage[]
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface Blueprint {
  title?: string
  target_audience?: string
  genre?: string
  style?: string
  tone?: string
  one_sentence_summary?: string
  full_synopsis?: string
  world_setting?: any
  characters?: Character[]
  relationships?: any[]
  chapter_outline?: ChapterOutline[]
}

export interface Character {
  name: string
  description: string
  identity?: string
  personality?: string
  goals?: string
  abilities?: string
  relationship_to_protagonist?: string
  is_protagonist?: boolean
}

export interface ChapterOutline {
  chapter_number: number
  title: string
  summary: string
}

export interface ChapterVersion {
  content: string
  style?: string
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content: string | null
  versions: string[] | null  // versions是字符串数组，不是对象数组
  evaluation: string | null
  generation_status: 'not_generated' | 'generating' | 'evaluating' | 'selecting' | 'failed' | 'evaluation_failed' | 'waiting_for_confirm' | 'successful'
  word_count?: number  // 字数统计
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ConverseResponse {
  ai_message: string
  ui_control: UIControl
  conversation_state: any
  is_complete: boolean
  ready_for_blueprint?: boolean  // 新增：表示准备生成蓝图
}

export interface BlueprintGenerationResponse {
  blueprint: Blueprint
  ai_message: string
}

export interface UIControl {
  type: 'single_choice' | 'text_input'
  options?: Array<{ id: string; label: string }>
  placeholder?: string
}

export interface ChapterGenerationResponse {
  versions: ChapterVersion[] // Renamed from chapter_versions for consistency
  evaluation: string | null
  ai_message: string
  chapter_number: number
}

export interface ChapterOutlineConverseResponse {
  ai_message: string
  proposed_outline?: {
    title: string
    summary: string
  }
}

export interface OutlineChapterPreview {
  chapter_number: number
  title: string
  summary: string
  narrative_phase?: string
  story_progress?: string
  foreshadowing?: {
    plant: string[]
    payoff: string[]
  }
  emotion_hook?: string
}

export interface OutlinePreviewResponse {
  chapters: OutlineChapterPreview[]
  new_characters: any[]
  new_relationships: any[]
  new_locations: any[]
  new_factions: any[]
  foreshadowing_plants: { chapter_number: number; content: string }[]
  foreshadowing_payoffs: { chapter_number: number; content: string }[]
  ai_message?: string
}

export interface DeleteNovelsResponse {
  status: string
  message: string
}

export interface SyncWorldSettingResult {
  new_locations: Array<{ name: string; description: string }>
  new_factions: Array<{ name: string; description: string }>
  total_locations: number
  total_factions: number
  added_count: number
}

// 内容型Section（对应后端NovelSectionType枚举）
export type NovelSectionType = 'overview' | 'world_setting' | 'characters' | 'relationships' | 'chapter_outline' | 'chapters'

// 分析型Section（不属于NovelSectionType，使用独立的analytics API）
export type AnalysisSectionType = 'emotion_curve' | 'foreshadowing'

// 所有Section的联合类型
export type AllSectionType = NovelSectionType | AnalysisSectionType

export interface NovelSectionResponse {
  section: NovelSectionType
  data: Record<string, any>
}

// API 函数
const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`

export class NovelAPI {
  static async createNovel(title: string, initialPrompt: string): Promise<NovelProject> {
    return request(NOVELS_BASE, {
      method: 'POST',
      body: JSON.stringify({ title, initial_prompt: initialPrompt })
    })
  }

  static async importNovel(file: File): Promise<{ id: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return request(`${NOVELS_BASE}/import`, {
      method: 'POST',
      body: formData,
      headers: {
        // 让 browser 自动设置 Content-Type 为 multipart/form-data，不手动设置
      }
    })
  }

  static async getNovel(projectId: string): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}`)
  }

  static async getChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return request(`${NOVELS_BASE}/${projectId}/chapters/${chapterNumber}`)
  }

  static async getSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return request(`${NOVELS_BASE}/${projectId}/sections/${section}`)
  }

  static async converseConcept(
    projectId: string,
    userInput: any,
    conversationState: any = {}
  ): Promise<ConverseResponse> {
    const formattedUserInput = userInput || { id: null, value: null }
    return request(`${NOVELS_BASE}/${projectId}/concept/converse`, {
      method: 'POST',
      body: JSON.stringify({
        user_input: formattedUserInput,
        conversation_state: conversationState
      })
    })
  }

  static async generateBlueprint(projectId: string): Promise<BlueprintGenerationResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate`, {
      method: 'POST'
    })
  }

  static async saveBlueprint(projectId: string, blueprint: Blueprint): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/save`, {
      method: 'POST',
      body: JSON.stringify(blueprint)
    })
  }

  static async generateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/generate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async evaluateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async selectChapterVersion(
    projectId: string,
    chapterNumber: number,
    versionIndex: number
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/select`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        version_index: versionIndex
      })
    })
  }

  static async getAllNovels(): Promise<NovelProjectSummary[]> {
    return request(NOVELS_BASE)
  }

  static async deleteNovels(projectIds: string[]): Promise<DeleteNovelsResponse> {
    return request(NOVELS_BASE, {
      method: 'DELETE',
      body: JSON.stringify(projectIds)
    })
  }

  static async updateChapterOutline(
    projectId: string,
    chapterOutline: ChapterOutline,
    aiMessage?: string
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/update-outline`, {
      method: 'POST',
      body: JSON.stringify({
        ...chapterOutline,
        ai_message: aiMessage || null
      })
    })
  }

  static async converseChapterOutline(
    projectId: string,
    chapterNumber: number,
    userMessage: string,
    conversationHistory: Array<{ role: string; content: string }> = []
  ): Promise<ChapterOutlineConverseResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline-converse`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        user_message: userMessage,
        conversation_history: conversationHistory
      })
    })
  }

  static async deleteChapter(
    projectId: string,
    chapterNumbers: number[]
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/delete`, {
      method: 'POST',
      body: JSON.stringify({ chapter_numbers: chapterNumbers })
    })
  }

  static async generateChapterOutline(
    projectId: string,
    startChapter: number,
    numChapters: number,
    userHint?: string
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline`, {
      method: 'POST',
      body: JSON.stringify({
        start_chapter: startChapter,
        num_chapters: numChapters,
        user_hint: userHint || null
      })
    })
  }

  static async previewChapterOutline(
    projectId: string,
    startChapter: number,
    numChapters: number,
    userHint?: string,
    totalChapters?: number
  ): Promise<OutlinePreviewResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline/preview`, {
      method: 'POST',
      body: JSON.stringify({
        start_chapter: startChapter,
        num_chapters: numChapters,
        user_hint: userHint || null,
        total_chapters: totalChapters || null
      })
    })
  }

  static async confirmChapterOutline(
    projectId: string,
    startChapter: number,
    previewData: Record<string, any>
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline/confirm`, {
      method: 'POST',
      body: JSON.stringify({
        start_chapter: startChapter,
        preview_data: previewData
      })
    })
  }

  static async updateBlueprint(projectId: string, data: Record<string, any>): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
  }

  /**
   * 同步世界设定（从章节大纲和摘要中提取地点和阵营）
   */
  static async syncWorldSetting(projectId: string): Promise<SyncWorldSettingResult> {
    return request(`${API_BASE_URL}/api/projects/${projectId}/world-setting/sync`, {
      method: 'POST'
    })
  }

  static async replaceKeyLocations(projectId: string, items: any[]): Promise<any> {
    return request(`${API_BASE_URL}/api/projects/${projectId}/key-locations/replace-all`, {
      method: 'PUT',
      body: JSON.stringify(items)
    })
  }

  static async replaceFactions(projectId: string, items: any[]): Promise<any> {
    return request(`${API_BASE_URL}/api/projects/${projectId}/factions/replace-all`, {
      method: 'PUT',
      body: JSON.stringify(items)
    })
  }

  static async editChapterContent(
    projectId: string,
    chapterNumber: number,
    content: string
  ): Promise<Chapter> {
    return request(`${WRITER_BASE}/${projectId}/chapters/edit-fast`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        content: content
      })
    })
  }
}


// 优化相关类型定义
export interface EmotionBeat {
  primary_emotion: string
  intensity: number
  curve: {
    start: number
    peak: number
    end: number
  }
  turning_point: string
}

export interface OptimizeRequest {
  project_id: string
  chapter_number: number
  dimension: 'dialogue' | 'environment' | 'psychology' | 'logic' | 'rhythm'
  additional_notes?: string
}

export interface OptimizeResponse {
  optimized_content: string
  optimization_notes: string
  dimension: string
}

export interface StartOptimizeResponse {
  task_id: string
  status: string
  message: string
}

export interface OptimizeTaskStatusResponse {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | string
  dimension: string
  project_id: string
  chapter_number: number
  original_content?: string | null
  optimized_content?: string | null
  optimization_notes?: string | null
  error_message?: string | null
}

export interface SummaryResponse {
  summary: string | null
  has_summary: boolean
}

// 优化API
const OPTIMIZER_BASE = `${API_BASE_URL}${API_PREFIX}/optimizer`

export class OptimizerAPI {
  /**
   * 对章节内容进行分层优化
   */
  static async optimizeChapter(optimizeReq: OptimizeRequest): Promise<OptimizeResponse> {
    return request(`${OPTIMIZER_BASE}/optimize`, {
      method: 'POST',
      body: JSON.stringify(optimizeReq)
    })
  }

  /**
   * 异步启动章节优化任务
   */
  static async optimizeChapterAsync(optimizeReq: OptimizeRequest): Promise<StartOptimizeResponse> {
    return request(`${OPTIMIZER_BASE}/optimize-async`, {
      method: 'POST',
      body: JSON.stringify(optimizeReq)
    })
  }

  /**
   * 查询优化任务状态
   */
  static async getOptimizeTaskStatus(taskId: string): Promise<OptimizeTaskStatusResponse> {
    return request(`${OPTIMIZER_BASE}/optimize-task/${taskId}`, {
      method: 'GET'
    })
  }

  /**
   * 获取章节最近一次优化结果（含进行中状态）
   */
  static async getLatestOptimizationResult(
    projectId: string,
    chapterNumber: number
  ): Promise<OptimizeTaskStatusResponse> {
    const params = new URLSearchParams({
      project_id: projectId,
      chapter_number: chapterNumber.toString()
    })
    return request(`${OPTIMIZER_BASE}/latest-optimization-result?${params}`, {
      method: 'GET'
    })
  }

  /**
   * 应用优化后的内容到章节
   */
  static async applyOptimization(
    projectId: string,
    chapterNumber: number,
    optimizedContent: string
  ): Promise<{ status: string; message: string }> {
    const params = new URLSearchParams({
      project_id: projectId,
      chapter_number: chapterNumber.toString(),
      optimized_content: optimizedContent
    })
    return request(`${OPTIMIZER_BASE}/apply-optimization?${params}`, {
      method: 'POST'
    })
  }

  /**
   * 获取章节摘要
   */
  static async getChapterSummary(
    projectId: string,
    chapterNumber: number
  ): Promise<SummaryResponse> {
    return request(`${OPTIMIZER_BASE}/summary/${projectId}/${chapterNumber}`, {
      method: 'GET'
    })
  }

  /**
   * 立即生成章节摘要并入向量库
   */
  static async generateChapterSummary(
    projectId: string,
    chapterNumber: number
  ): Promise<{ status: string; message: string }> {
    const params = new URLSearchParams({
      project_id: projectId,
      chapter_number: chapterNumber.toString()
    })
    return request(`${OPTIMIZER_BASE}/generate-summary?${params}`, {
      method: 'POST'
    })
  }

  /**
   * 更新章节摘要
   */
  static async updateChapterSummary(
    projectId: string,
    chapterNumber: number,
    summary: string
  ): Promise<{ status: string; message: string }> {
    return request(`${OPTIMIZER_BASE}/summary`, {
      method: 'PUT',
      body: JSON.stringify({
        project_id: projectId,
        chapter_number: chapterNumber,
        summary: summary
      })
    })
  }

  /**
   * 将优化经验追加到写作风格库
   */
  static async appendWritingStyle(
    dimension: string,
    additionalNotes: string,
    optimizationNotes: string
  ): Promise<{ status: string; message: string; summary: string }> {
    return request(`${OPTIMIZER_BASE}/append-style`, {
      method: 'POST',
      body: JSON.stringify({
        dimension,
        additional_notes: additionalNotes,
        optimization_notes: optimizationNotes
      })
    })
  }
}
