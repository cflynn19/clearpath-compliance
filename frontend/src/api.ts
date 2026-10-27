// Shapes mirror backend/app/rules/models.py and backend/app/analysis.py.

export type Product = 'personal_loan' | 'credit_card' | 'mortgage'
export type Channel = 'email' | 'social' | 'landing_page' | 'affiliate_page' | 'search_ad'
export type FlagType = 'check_failed' | 'needs_judgment'

export interface Asset {
  body: string
  product: Product
  channel: Channel
  subject?: string | null
}

export interface Span {
  quote: string
  field: 'body' | 'subject'
  start: number
  end: number
}

export interface Flag {
  rule_id: string
  rule_name: string
  type: FlagType
  citation: string
  why: string
  spans: Span[]
}

export interface AiStatus {
  status: 'ran' | 'cached' | 'limited' | 'unavailable' | 'disabled'
  message: string
  remaining_this_hour: number
  limit_per_hour: number
  dropped: number
}

export interface AnalyzeResult {
  flags: Flag[]
  ai: AiStatus
}

export interface Limits {
  ai_enabled: boolean
  remaining_this_hour: number
  limit_per_hour: number
}

export const PRODUCTS: Record<Product, string> = {
  personal_loan: 'Personal loan',
  credit_card: 'Credit card',
  mortgage: 'Mortgage prequalification',
}

export const CHANNELS: Record<Channel, string> = {
  email: 'Email',
  social: 'Social post',
  landing_page: 'Landing page',
  affiliate_page: 'Affiliate page',
  search_ad: 'Search ad',
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join('; ')
      : body?.detail
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export type AssetStatus = 'in_review' | 'approved' | 'rejected'
export type FlagStatus = 'open' | 'dismissed' | 'acknowledged'

export const STATUS_LABEL: Record<AssetStatus, string> = {
  in_review: 'In review',
  approved: 'Approved',
  rejected: 'Rejected',
}

export interface StoredFlag extends Flag {
  id: number
  status: FlagStatus
  reason: string | null
  note: string | null
  resolved_by: string | null
  resolved_at: string | null
}

export interface ReviewEvent {
  id: number
  actor: string
  action: string
  detail: Record<string, unknown>
  created_at: string
}

export interface AssetSummary {
  id: number
  title: string
  submitter: string
  product: Product
  channel: Channel
  status: AssetStatus
  created_at: string
  decided_at: string | null
  open_failed: number
  open_judgment: number
  total: number
}

export interface AssetDetail extends Omit<AssetSummary, 'open_failed' | 'open_judgment' | 'total'> {
  decided_by: string | null
  decision_note: string | null
  version: { number: number; subject: string | null; body: string; ai: AiStatus; created_at: string }
  flags: StoredFlag[]
  events: ReviewEvent[]
}

export interface NewAsset extends Asset {
  title?: string
  submitter?: string
}

export interface Rule {
  id: string
  name: string
  type: FlagType
  citation: string
  description: string
  products: Product[]
  channels: Channel[]
  enabled: boolean
  source: string
  stats: { flagged: number; dismissed: number; reasons: Record<string, number> }
}

export interface ReviewConfig {
  actor: string
  dismiss_reasons: Record<string, string>
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const listAssets = () => request<AssetSummary[]>('/api/assets')
export const getAsset = (id: number) => request<AssetDetail>(`/api/assets/${id}`)
export const createAsset = (asset: NewAsset) => request<AssetDetail>('/api/assets', post(asset))
export const dismissFlag = (id: number, reason: string, note: string) =>
  request<AssetDetail>(`/api/flags/${id}/dismiss`, post({ reason, note }))
export const acknowledgeFlag = (id: number) => request<AssetDetail>(`/api/flags/${id}/acknowledge`, post())
export const reopenFlag = (id: number) => request<AssetDetail>(`/api/flags/${id}/reopen`, post())
export const decide = (id: number, decision: 'approve' | 'reject', note: string) =>
  request<AssetDetail>(`/api/assets/${id}/decision`, post({ decision, note }))
export const getRules = () => request<Rule[]>('/api/rules')

export interface NewRule {
  name: string
  kind: 'phrases' | 'instruction'
  phrases: string[]
  instruction: string
  products: Product[]
  channels: Channel[]
}
export const createRule = (rule: NewRule) => request<Rule[]>('/api/rules', post(rule))
export const toggleRule = (id: string, enabled: boolean) =>
  request<Rule[]>(`/api/rules/${id}`, { ...post({ enabled }), method: 'PATCH' })
export const deleteRule = (id: string) => request<Rule[]>(`/api/rules/${id}`, { method: 'DELETE' })
export const getReviewConfig = () => request<ReviewConfig>('/api/review-config')
export const resetDemo = () => request<{ seeded: number }>('/api/demo/reset', post())

export function analyze(asset: Asset): Promise<AnalyzeResult> {
  return request('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(asset),
  })
}

export function getLimits(): Promise<Limits> {
  return request('/api/limits')
}
