// AIMETA P=趋势API客户端_排行榜和趋势分析|R=排行榜_趋势报告_数据刷新|NR=不含UI逻辑|E=api:trend|X=internal|A=TrendAPI对象|D=fetch|S=net|RD=./README.ai
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'

const request = async (url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers,
  })

  if (authStore.isAuthenticated && authStore.token) {
    headers.set('Authorization', `Bearer ${authStore.token}`)
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401) {
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

// ==================== 类型定义 ====================

export interface PlatformInfo {
  id: string
  name: string
  categories: Record<string, string>
  meta?: {
    gender_tabs?: Record<string, string>
    category_groups?: Record<string, Record<string, string>>
    ranking_types?: Record<string, string>
  }
}

export interface RankingBook {
  rank: number
  title: string
  author: string
  genre: string
  word_count: string
  description: string
  tags: string
  heat_score: number
  cover_url: string
  book_url: string
}

export interface GenreDistribution {
  genres: Record<string, { count: number; percentage: number }>
  total: number
  snapshot_date: string | null
}

export interface TrendReport {
  platform: string
  category?: string
  report_date: string
  genre_distribution?: Record<string, any>
  hot_keywords?: string[]
  trend_summary?: string
  hot_elements?: Array<{ element: string; frequency: string; description: string }>
  reader_preferences?: Record<string, any>
  opportunities?: Array<{ type: string; description: string }>
  creation_suggestions?: string[]
  ai_full_report?: string
  error?: string
}

const TRENDS_BASE = `${API_BASE_URL}${API_PREFIX}/trends`

// ==================== API ====================

export class TrendAPI {
  static async getPlatforms(): Promise<{ platforms: PlatformInfo[] }> {
    return request(`${TRENDS_BASE}/platforms`)
  }

  static async getRanking(
    platform: string,
    category: string = 'hot',
    limit: number = 50,
  ): Promise<{ platform: string; category: string; count: number; books: RankingBook[] }> {
    const params = new URLSearchParams({
      category,
      limit: limit.toString(),
    })
    return request(`${TRENDS_BASE}/${platform}/ranking?${params}`)
  }

  static async getGenreDistribution(
    platform: string,
    category: string = 'hot',
  ): Promise<GenreDistribution> {
    const params = new URLSearchParams({ category })
    return request(`${TRENDS_BASE}/${platform}/genres?${params}`)
  }

  static async getTrendReport(
    platform: string,
    category: string = 'all',
    forceRegenerate: boolean = false,
  ): Promise<TrendReport> {
    const params = new URLSearchParams({
      category,
      force_regenerate: forceRegenerate.toString(),
    })
    return request(`${TRENDS_BASE}/${platform}/report?${params}`)
  }

  static async refreshData(platform: string, category: string = 'hot'): Promise<{ status: string; message: string; count: number }> {
    const params = new URLSearchParams({ category })
    return request(`${TRENDS_BASE}/${platform}/refresh?${params}`, {
      method: 'POST',
    })
  }

  static async importData(
    platform: string,
    text: string,
    category: string = 'manual',
  ): Promise<{ status: string; count: number; books: RankingBook[] }> {
    return request(`${TRENDS_BASE}/import`, {
      method: 'POST',
      body: JSON.stringify({ platform, category, text, format: 'auto' }),
    })
  }

  static async getCreationSuggestion(context: string = ''): Promise<{ suggestion: string }> {
    const params = new URLSearchParams({ context })
    return request(`${TRENDS_BASE}/suggestion?${params}`)
  }

  static async deletePlatformData(platform: string): Promise<{ status: string; platform: string; deleted: { snapshots: number; books: number; reports: number } }> {
    return request(`${TRENDS_BASE}/${platform}`, {
      method: 'DELETE',
    })
  }
}
