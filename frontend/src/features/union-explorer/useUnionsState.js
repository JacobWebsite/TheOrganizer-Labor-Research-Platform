import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

const FILTER_KEYS = ['q', 'aff_abbr', 'sector', 'state', 'min_members', 'has_employers']

/**
 * Syncs unions page filter/page state with URL search params.
 */
export function useUnionsState() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo(() => ({
    q: searchParams.get('q') || '',
    aff_abbr: searchParams.get('aff_abbr') || '',
    sector: searchParams.get('sector') || '',
    state: searchParams.get('state') || '',
    min_members: searchParams.get('min_members') || '',
    has_employers: searchParams.get('has_employers') || '',
  }), [searchParams])

  const page = Number(searchParams.get('page') || '1')

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

  const hasActiveFilters = FILTER_KEYS.some((k) => searchParams.get(k))

  return { filters, page, hasActiveFilters, setFilter, clearFilter, clearAll, setPage }
}
