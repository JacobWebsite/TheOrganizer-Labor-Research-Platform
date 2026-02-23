import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

const FILTER_KEYS = ['status', 'q']

/**
 * Syncs research page filter/page state with URL search params.
 */
export function useResearchState() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo(() => ({
    status: searchParams.get('status') || '',
    q: searchParams.get('q') || '',
  }), [searchParams])

  const page = Number(searchParams.get('page') || '1')
  const PAGE_SIZE = 20

  const setFilter = useCallback((key, value) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) {
        next.set(key, value)
      } else {
        next.delete(key)
      }
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

  const hasActiveFilters = FILTER_KEYS.some((k) => searchParams.get(k))

  return { filters, page, PAGE_SIZE, hasActiveFilters, setFilter, clearFilter, clearAll, setPage }
}
