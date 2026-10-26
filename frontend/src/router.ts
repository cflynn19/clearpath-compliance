import { useEffect, useState } from 'react'

// A tiny hash router: four pages don't need a routing library.
export type Route =
  | { page: 'queue' }
  | { page: 'review'; id: number }
  | { page: 'new' }
  | { page: 'rules' }

export function parseRoute(hash: string): Route {
  const [page, id] = hash.replace(/^#\/?/, '').split('/')
  if (page === 'review' && Number(id)) return { page: 'review', id: Number(id) }
  if (page === 'new') return { page: 'new' }
  if (page === 'rules') return { page: 'rules' }
  return { page: 'queue' }
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
  review: (id: number) => `#/review/${id}`,
  new: '#/new',
  rules: '#/rules',
}
