import { useEffect, useState } from 'react'

// A tiny hash router: a handful of pages don't need a routing library.
export type Route =
  | { page: 'queue'; rule?: string }
  | { page: 'review'; id: number }
  | { page: 'new' }
  | { page: 'rules'; focus?: string }
  | { page: 'insights' }

export function parseRoute(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const params = new URLSearchParams(query)
  const [page, id] = path.split('/')
  if (page === 'review' && Number(id)) return { page: 'review', id: Number(id) }
  if (page === 'new') return { page: 'new' }
  if (page === 'rules') return { page: 'rules', focus: params.get('focus') ?? undefined }
  if (page === 'insights') return { page: 'insights' }
  return { page: 'queue', rule: params.get('rule') ?? undefined }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      setRoute(parseRoute(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const href = {
  queue: '#/queue',
  queueForRule: (ruleId: string) => `#/queue?rule=${encodeURIComponent(ruleId)}`,
  review: (id: number) => `#/review/${id}`,
  new: '#/new',
  rules: '#/rules',
  rule: (ruleId: string) => `#/rules?focus=${encodeURIComponent(ruleId)}`,
  insights: '#/insights',
}
