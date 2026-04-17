import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ----------------------------------------------------------------
// Types
// ----------------------------------------------------------------

export interface DominantColor {
  hex: string
  percentage: number
}

export interface Product {
  id: string
  source: string
  external_id: string
  name: string
  brand: string | null
  url: string
  image_url: string | null
  price: number
  currency: string
  color_name: string | null
  dominant_colors: DominantColor[] | null
  color_match_score: number | null
  closest_palette_color: string | null
  fabric_raw: string | null
  fabric_parsed: Array<{ fiber: string; percentage: number }> | null
  fabric_score: number | null
  has_excluded_fabric: boolean
  description: string | null
  in_stock: boolean
  is_priority_brand: boolean
  first_seen_at: string
  last_seen_at: string
}

export interface Match {
  id: string
  product: Product
  color_score: number
  fabric_score: number
  overall_score: number
  is_borderline_color: boolean
  claude_style_analysis: string | null
  claude_color_reasoning: string | null
  claude_flags: string[] | null
  is_new: boolean
  matched_at: string
}

export interface MatchListResponse {
  items: Match[]
  total: number
  page: number
  page_size: number
}

export interface Feedback {
  id: string
  match_id: string
  action: 'accepted' | 'rejected' | 'saved'
  note: string | null
  created_at: string
}

export interface WishlistItem {
  id: string
  match_id: string
  action: 'accepted' | 'saved'
  note: string | null
  created_at: string
  match: Match
}

export interface Alert {
  id: string
  product: Product
  alert_type: 'price_drop' | 'restock' | 'new_match'
  previous_price: number | null
  current_price: number | null
  message: string | null
  is_read: boolean
  created_at: string
}

// ----------------------------------------------------------------
// API helpers
// ----------------------------------------------------------------

export const matchesApi = {
  list: (params: Record<string, unknown> = {}) =>
    api.get<MatchListResponse>('/matches/', { params }),

  markRead: (matchId: string) =>
    api.patch(`/matches/${matchId}/read`),
}

export const feedbackApi = {
  submit: (matchId: string, action: string, note?: string) =>
    api.post<Feedback>(`/feedback/${matchId}`, { action, note }),

  wishlist: () =>
    api.get<WishlistItem[]>('/feedback/wishlist'),
}

export const alertsApi = {
  list: (unreadOnly = false) =>
    api.get<Alert[]>(`/alerts/?unread_only=${unreadOnly}`),

  markRead: (alertId: string) =>
    api.patch(`/alerts/${alertId}/read`),

  markAllRead: () =>
    api.patch('/alerts/read-all'),
}

export const scraperApi = {
  run: (source?: string) =>
    api.post('/scraper/run', null, { params: source ? { source } : {} }),
}
