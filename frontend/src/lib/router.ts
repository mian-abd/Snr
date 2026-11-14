import { useEffect, useState } from 'react'

/** A tiny hash router: every page has a shareable URL and the server stays a static host. */
export function currentPath() {
  const raw = window.location.hash.replace(/^#/, '')
  return raw.startsWith('/') ? raw : '/'
}

export function useRoute() {
  const [path, setPath] = useState(currentPath)
  useEffect(() => {
    const update = () => setPath(currentPath())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const [pathname, query = ''] = path.split('?')
  const segments = pathname.split('/').filter(Boolean)
  return { path: pathname, segments, query: new URLSearchParams(query) }
}

export function navigate(path: string) {
  if (currentPath() !== path) window.location.hash = path
  window.scrollTo({ top: 0 })
}
