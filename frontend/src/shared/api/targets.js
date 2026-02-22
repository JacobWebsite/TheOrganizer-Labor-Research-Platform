import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Fetch non-union target employers with filters and pagination.
 */
export function useNonUnionTargets({
  q, state, naics, min_employees, max_employees,
  is_federal_contractor, is_nonprofit, min_quality,
  sort = 'quality', order = 'desc', page = 1, limit = 50,
  enabled = true,
} = {}) {
  return useQuery({
    queryKey: ['non-union-targets', { q, state, naics, min_employees, max_employees, is_federal_contractor, is_nonprofit, min_quality, sort, order, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (state) params.set('state', state)
      if (naics) params.set('naics', naics)
      if (min_employees != null) params.set('min_employees', String(min_employees))
      if (max_employees != null) params.set('max_employees', String(max_employees))
      if (is_federal_contractor != null) params.set('is_federal_contractor', String(is_federal_contractor))
      if (is_nonprofit != null) params.set('is_nonprofit', String(is_nonprofit))
      if (min_quality != null) params.set('min_quality', String(min_quality))
      params.set('sort', sort)
      params.set('order', order)
      params.set('page', String(page))
      params.set('limit', String(limit))
      return apiClient.get(`/api/master/non-union-targets?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

/**
 * Fetch master employer stats (total, distributions, flags).
 */
export function useTargetStats() {
  return useQuery({
    queryKey: ['master-stats'],
    queryFn: () => apiClient.get('/api/master/stats'),
    staleTime: 15 * 60 * 1000, // 15 minutes
  })
}

/**
 * Fetch master employer detail with enrichment data.
 */
export function useTargetDetail(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['master-detail', id],
    queryFn: () => apiClient.get(`/api/master/${id}`),
    enabled: enabled && !!id,
  })
}
