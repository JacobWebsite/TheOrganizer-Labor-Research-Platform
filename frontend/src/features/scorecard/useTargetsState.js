import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

const FILTER_KEYS = ['q', 'state', 'naics', 'min_employees', 'max_employees', 'is_federal_contractor', 'is_nonprofit', 'min_quality', 'has_enforcement', 'min_signals']

/**
 * Syncs targets page filter/sort/page state with URL search params.
 */
export function useTargetsState() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = useMemo(() => ({
    q: searchParams.get('q') || '',
    state: searchParams.get('state') || '',
    naics: searchParams.get('naics') || '',
    min_employees: searchParams.get('min_employees') || '',
    max_employees: searchParams.get('max_employees') || '',
    is_federal_contractor: searchParams.get('is_federal_contractor') || '',
    is_nonprofit: searchParams.get('is_nonprofit') || '',
    min_quality: searchParams.get('min_quality') || '',
    has_enforcement: searchParams.get('has_enforcement') || '',
    min_signals: searchParams.get('min_signals') || '',
  }), [searchParams])

  const sort = searchParams.get('sort') || 'quality'
  const order = searchParams.get('order') || 'desc'
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

  const setSort = useCallback((sortKey) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      // Map sort keys to sort + order
      if (sortKey === 'quality') {
        next.set('sort', 'quality')
        next.set('order', 'desc')
      } else if (sortKey === 'employees') {
        next.set('sort', 'employees')
        next.set('order', 'desc')
      } else if (sortKey === 'name') {
        next.set('sort', 'name')
        next.set('order', 'asc')
      }
      next.delete('page')
      return next
    })
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

  return { filters, sort, order, page, hasActiveFilters, setFilter, clearFilter, clearAll, setSort, setPage }
}
