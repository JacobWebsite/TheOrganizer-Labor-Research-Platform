import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

const PARAM_KEYS = ['q', 'state', 'naics', 'source_type', 'has_union', 'page']

/**
 * Syncs search/filter state with URL search params.
 */
export function useSearchState() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo(() => ({
    q: searchParams.get('q') || '',
    state: searchParams.get('state') || '',
    naics: searchParams.get('naics') || '',
    source_type: searchParams.get('source_type') || '',
    has_union: searchParams.get('has_union') || '',
  }), [searchParams])

  const page = Number(searchParams.get('page') || '1')

  const hasActiveSearch = PARAM_KEYS.some((k) => searchParams.get(k))

  const setFilter = useCallback((key, value) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      // Reset page when filters change
      if (key !== 'page') next.delete('page')
      return next
    })
  }, [setSearchParams])

  const clearFilter = useCallback((key) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete(key)
      next.delete('page')
      return next
    })
  }, [setSearchParams])

  const clearAll = useCallback(() => {
    setSearchParams({})
  }, [setSearchParams])

  const setPage = useCallback((p) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (p > 1) {
        next.set('page', String(p))
      } else {
        next.delete('page')
      }
      return next
    })
  }, [setSearchParams])

  return { filters, page, hasActiveSearch, setFilter, clearFilter, clearAll, setPage }
}
