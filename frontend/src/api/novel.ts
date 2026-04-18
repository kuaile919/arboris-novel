// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// API 配置
// 在生产环境中使用相对路径，在开发环境中使用绝对路径
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'

export class APIError extends Error {
  status: number
  data: any

  constructor(message: string, status: number, data: any = null) {
    super(message)
    this.name = 'APIError'
    this.status = status
    this.data = data
  }
}

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
    throw new APIError(errorData.detail || `请求失败，状态码: ${response.status}`, response.status, errorData)
  }

  if (response.status === 204) {
    return undefined
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
  total_chapters?: number
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
  mark_tag?: 'none' | 'todo_fix' | 'todo_check' | 'todo_polish' | null
  foreshadowing?: {
    plant: string[]
    payoff: string[]
  }
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

export interface ChapterRuntimeStatus {
  chapter_number: number
  generation_status: Chapter['generation_status']
  word_count: number
  updated_at: string | null
  has_content: boolean
  versions_count: number
  has_evaluation: boolean
  selected_version_id: number | null
}

export interface WritingStyleLibrary {
  outline_text: string
  chapter_text: string
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
  type: 'single_choice' | 'text_input' | 'info_display'
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
  new_characters?: OutlineEntityItem[]
  new_locations?: OutlineEntityItem[]
  new_factions?: OutlineEntityItem[]
  foreshadowing_plants?: OutlineForeshadowingItem[]
  foreshadowing_payoffs?: OutlineForeshadowingItem[]
}

export interface OutlineEntityItem {
  name: string
  description?: string
  first_appear_chapter?: number | null
}

export interface OutlineForeshadowingItem {
  content: string
  target_reveal_chapter?: number | null
  planted_chapter?: number | null
  importance?: string | null
  keywords?: string[]
  foreshadowing_id?: number | null
}

export interface ChapterOutlineConverseContextResponse {
  chapter_number: number
  title: string
  summary: string
  narrative_phase?: string | null
  story_progress?: string | null
  emotion_hook?: string | null
  new_characters: OutlineEntityItem[]
  new_locations: OutlineEntityItem[]
  new_factions: OutlineEntityItem[]
  foreshadowing_plants: OutlineForeshadowingItem[]
  foreshadowing_payoffs: OutlineForeshadowingItem[]
}

export interface ApplyChapterOutlineConverseRequest {
  chapter_number: number
  title: string
  summary: string
  ai_message?: string
  new_characters?: Record<string, any>[]
  new_locations?: Record<string, any>[]
  new_factions?: Record<string, any>[]
  foreshadowing_plants?: Record<string, any>[]
  foreshadowing_payoffs?: Record<string, any>[]
}

export interface BlueprintSettingImpactAnalysis {
  impact_level?: 'low' | 'medium' | 'high' | string
  summary?: string
  impacted_sections?: string[]
  impacted_chapters?: number[]
  recommended_actions?: string[]
  [key: string]: any
}

export interface BlueprintSettingChatMessage {
  id?: number
  role: 'user' | 'assistant'
  message: string
  phase?: string
  created_at?: string
  proposed_patch?: Record<string, any> | null
  impact_analysis?: BlueprintSettingImpactAnalysis | null
  applied_to_blueprint?: boolean
  source?: string
  metadata?: Record<string, any> | null
}

export interface BlueprintSettingHistoryResponse {
  messages?: BlueprintSettingChatMessage[]
  history?: BlueprintSettingChatMessage[]
}

export interface BlueprintSettingConverseResponse {
  message?: BlueprintSettingChatMessage
  messages?: BlueprintSettingChatMessage[]
  history?: BlueprintSettingChatMessage[]
  ai_message?: string
  proposed_patch?: Record<string, any> | null
  impact_analysis?: BlueprintSettingImpactAnalysis | null
  need_confirm?: boolean
  latest_message_id?: number | null
}

export interface BlueprintSettingApplyResponse {
  project?: NovelProject
  ai_message?: string
  message?: string
  [key: string]: any
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

export interface ForeshadowingAnalyticsItem {
  id: string
  description: string
  planted_chapter: number
  planted_chapter_title: string
  expected_payoff_chapter?: number
  actual_payoff_chapter?: number
  status: 'planted' | 'paid_off' | 'overdue'
  importance: 'short' | 'medium' | 'long'
}

export interface ForeshadowingAnalyticsResponse {
  project_id: string
  project_title: string
  total_foreshadowings: number
  planted_count: number
  paid_off_count: number
  overdue_count: number
  foreshadowings: ForeshadowingAnalyticsItem[]
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

export interface IMAKnowledgeBase {
  id: string
  name: string
  cover_url?: string | null
  description?: string | null
  recommended_questions: string[]
  member_count?: number | null
  content_count?: number | null
  creator?: string | null
  role_type?: string | null
}

export interface IMAKnowledgeBaseCollectionResponse {
  items: IMAKnowledgeBase[]
  next_cursor: string
  is_end: boolean
}

export interface IMAKnowledgePathEntry {
  id: string
  name: string
  is_root: boolean
}

export interface IMAKnowledgeItem {
  id: string
  title: string
  is_folder: boolean
  media_type: number
  parent_folder_id?: string | null
  tags: string[]
  highlight_content?: string | null
}

export interface IMAKnowledgeBaseDetailResponse {
  knowledge_base: IMAKnowledgeBase
}

export interface IMAKnowledgeItemListResponse {
  items: IMAKnowledgeItem[]
  current_path: IMAKnowledgePathEntry[]
  next_cursor: string
  is_end: boolean
}

export interface IMASearchResponse {
  items: IMAKnowledgeItem[]
  next_cursor: string
  is_end: boolean
  fallback_used: boolean
  fallback_provider?: string | null
  fallback_message?: string | null
  fallback_results: IMAFallbackSearchResult[]
}

export interface IMAFallbackSearchResult {
  title: string
  link: string
  snippet?: string | null
  date?: string | null
}

export interface IMAFileUploadResponse {
  message: string
  knowledge_base: IMAKnowledgeBase
  item: IMAKnowledgeItem
  duplicate_handling: 'original' | 'renamed'
  original_name: string
  final_name: string
}

export interface IMAUrlImportResult {
  url: string
  success: boolean
  media_id?: string | null
  error?: string | null
}

export interface IMAUrlImportResponse {
  message: string
  success_count: number
  failure_count: number
  results: IMAUrlImportResult[]
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
const PROJECTS_BASE = `${API_BASE_URL}${API_PREFIX}/projects`
const WRITER_PREFIX = '/api/writer'
const WRITER_API_BASE = `${API_BASE_URL}${WRITER_PREFIX}`
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`
const ANALYTICS_BASE = `${API_BASE_URL}${API_PREFIX}/analytics`

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

  static async getChapterRuntimeStatus(
    projectId: string,
    chapterNumber: number
  ): Promise<ChapterRuntimeStatus> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/status`)
  }

  static async getForeshadowingAnalytics(projectId: string): Promise<ForeshadowingAnalyticsResponse> {
    return request(`${ANALYTICS_BASE}/${projectId}/foreshadowing`)
  }

  static async updateForeshadowing(
    projectId: string,
    foreshadowingId: number,
    payload: {
      content?: string
      target_reveal_chapter?: number | null
      importance?: 'major' | 'minor' | 'subtle' | null
      keywords?: string[]
      author_note?: string | null
    }
  ): Promise<any> {
    return request(`${NOVELS_BASE}/${projectId}/foreshadowings/${foreshadowingId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static async deleteForeshadowing(projectId: string, foreshadowingId: number): Promise<{ status: string; message: string }> {
    return request(`${NOVELS_BASE}/${projectId}/foreshadowings/${foreshadowingId}`, {
      method: 'DELETE'
    })
  }

  static async getWritingStyleLibrary(): Promise<WritingStyleLibrary> {
    return request(`${WRITER_API_BASE}/style-library`)
  }

  static async updateWritingStyleLibrary(
    outlineText: string,
    chapterText: string
  ): Promise<WritingStyleLibrary> {
    return request(`${WRITER_API_BASE}/style-library`, {
      method: 'PUT',
      body: JSON.stringify({
        outline_text: outlineText,
        chapter_text: chapterText
      })
    })
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

  static async updateChapterMark(
    projectId: string,
    chapterNumber: number,
    markTag: 'none' | 'todo_fix' | 'todo_check' | 'todo_polish'
  ): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/chapters/mark`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        mark_tag: markTag
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

  static async getChapterOutlineConverseContext(
    projectId: string,
    chapterNumber: number
  ): Promise<ChapterOutlineConverseContextResponse> {
    return request(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/outline-converse/context`)
  }

  static async applyChapterOutlineConverse(
    projectId: string,
    payload: ApplyChapterOutlineConverseRequest
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline-converse/apply`, {
      method: 'POST',
      body: JSON.stringify(payload)
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

  static async getBlueprintSettingChatHistory(projectId: string): Promise<BlueprintSettingHistoryResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/setting-chat/history`, {
      method: 'GET'
    })
  }

  static async converseBlueprintSettingChat(
    projectId: string,
    userMessage: string
  ): Promise<BlueprintSettingConverseResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/setting-chat/converse`, {
      method: 'POST',
      body: JSON.stringify({
        user_message: userMessage
      })
    })
  }

  static async applyBlueprintSettingPatch(
    projectId: string,
    patch: Record<string, any>,
    assistantMessageId?: number | null
  ): Promise<BlueprintSettingApplyResponse | NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/setting-chat/apply`, {
      method: 'POST',
      body: JSON.stringify({
        patch,
        assistant_message_id: assistantMessageId ?? null
      })
    })
  }

  /**
   * 同步世界设定（从章节大纲和摘要中提取地点和阵营）
   */
  static async syncWorldSetting(projectId: string): Promise<SyncWorldSettingResult> {
    return request(`${PROJECTS_BASE}/${projectId}/world-setting/sync`, {
      method: 'POST'
    })
  }

  static async replaceKeyLocations(projectId: string, items: any[]): Promise<any> {
    return request(`${PROJECTS_BASE}/${projectId}/key-locations/replace-all`, {
      method: 'PUT',
      body: JSON.stringify(items)
    })
  }

  static async replaceFactions(projectId: string, items: any[]): Promise<any> {
    return request(`${PROJECTS_BASE}/${projectId}/factions/replace-all`, {
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

  static async getIMAAddableKnowledgeBases(
    projectId: string,
    cursor = '',
    limit = 20
  ): Promise<IMAKnowledgeBaseCollectionResponse> {
    const params = new URLSearchParams({
      cursor,
      limit: String(limit)
    })
    return request(`${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/addable?${params.toString()}`, {
      method: 'GET'
    })
  }

  static async searchIMAKnowledgeBases(
    projectId: string,
    query: string,
    cursor = '',
    limit = 20
  ): Promise<IMAKnowledgeBaseCollectionResponse> {
    const params = new URLSearchParams({
      query,
      cursor,
      limit: String(limit)
    })
    return request(`${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/search?${params.toString()}`, {
      method: 'GET'
    })
  }

  static async getIMAKnowledgeBase(
    projectId: string,
    knowledgeBaseId: string
  ): Promise<IMAKnowledgeBaseDetailResponse> {
    return request(`${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`, {
      method: 'GET'
    })
  }

  static async listIMAKnowledgeItems(
    projectId: string,
    knowledgeBaseId: string,
    options: { cursor?: string; limit?: number; folderId?: string | null } = {}
  ): Promise<IMAKnowledgeItemListResponse> {
    const params = new URLSearchParams({
      cursor: options.cursor || '',
      limit: String(options.limit || 20)
    })
    if (options.folderId) {
      params.set('folder_id', options.folderId)
    }
    return request(
      `${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/items?${params.toString()}`,
      {
        method: 'GET'
      }
    )
  }

  static async searchIMAKnowledgeItems(
    projectId: string,
    knowledgeBaseId: string,
    query: string,
    cursor = ''
  ): Promise<IMASearchResponse> {
    const params = new URLSearchParams({
      query,
      cursor
    })
    return request(
      `${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/search?${params.toString()}`,
      {
        method: 'GET'
      }
    )
  }

  static async uploadIMAKnowledgeFile(
    projectId: string,
    knowledgeBaseId: string,
    file: File,
    options: { folderId?: string | null; onDuplicate?: 'error' | 'rename' } = {}
  ): Promise<IMAFileUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    if (options.folderId) {
      formData.append('folder_id', options.folderId)
    }
    formData.append('on_duplicate', options.onDuplicate || 'error')
    return request(
      `${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/files/upload`,
      {
        method: 'POST',
        body: formData
      }
    )
  }

  static async importIMAUrls(
    projectId: string,
    knowledgeBaseId: string,
    urls: string[],
    folderId?: string | null
  ): Promise<IMAUrlImportResponse> {
    return request(
      `${PROJECTS_BASE}/${projectId}/ima/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/urls/import`,
      {
        method: 'POST',
        body: JSON.stringify({
          urls,
          folder_id: folderId || null
        })
      }
    )
  }

  static isAPIError(error: unknown): error is APIError {
    return error instanceof APIError
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

export interface CleanupOptimizationHistoryResponse {
  status: string
  deleted_count: number
  scope: 'chapter' | 'project' | 'user_all' | string
  keep_running: boolean
}

export interface SummaryResponse {
  summary: string | null
  has_summary: boolean
}

export interface PolishSelectionRequest {
  project_id: string
  chapter_number: number
  selected_text: string
  context_before?: string
  context_after?: string
  dimension?: 'dialogue' | 'environment' | 'psychology' | 'logic' | 'rhythm'
  additional_notes?: string
}

export interface PolishSelectionResponse {
  polished_text: string
  polish_notes: string
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
   * 清理历史优化任务记录
   */
  static async clearOptimizationHistory(
    projectId?: string,
    chapterNumber?: number,
    keepRunning: boolean = true
  ): Promise<CleanupOptimizationHistoryResponse> {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (typeof chapterNumber === 'number') params.set('chapter_number', chapterNumber.toString())
    params.set('keep_running', keepRunning ? 'true' : 'false')

    return request(`${OPTIMIZER_BASE}/optimization-history?${params}`, {
      method: 'DELETE'
    })
  }

  /**
   * 对选中的局部文本进行 AI 润色
   */
  static async polishSelection(
    polishReq: PolishSelectionRequest
  ): Promise<PolishSelectionResponse> {
    return request(`${OPTIMIZER_BASE}/polish-selection`, {
      method: 'POST',
      body: JSON.stringify(polishReq)
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
    return request(`${OPTIMIZER_BASE}/apply-optimization`, {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        chapter_number: chapterNumber,
        optimized_content: optimizedContent
      })
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
