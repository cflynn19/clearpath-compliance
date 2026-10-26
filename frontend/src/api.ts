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
