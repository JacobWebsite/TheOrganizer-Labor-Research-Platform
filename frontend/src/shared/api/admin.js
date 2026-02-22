import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Fetch system health (API + DB status). Auto-refreshes every 30s.
 */
export function useSystemHealth() {
  return useQuery({
    queryKey: ['system-health'],
    queryFn: () => apiClient.get('/api/health'),
    refetchInterval: 30000,
  })
}

/**
 * Fetch platform-wide statistics (employer counts, match totals, etc.).
 */
export function usePlatformStats() {
  return useQuery({
    queryKey: ['platform-stats'],
    queryFn: () => apiClient.get('/api/stats'),
    staleTime: 60000,
  })
}

/**
 * Fetch data freshness per source (row counts, latest dates, staleness flags).
 */
export function useDataFreshness() {
  return useQuery({
    queryKey: ['data-freshness'],
    queryFn: () => apiClient.get('/api/system/data-freshness'),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Fetch score version history.
 */
export function useScoreVersions() {
  return useQuery({
    queryKey: ['score-versions'],
    queryFn: () => apiClient.get('/api/admin/score-versions'),
  })
}

/**
 * Fetch match quality overview (totals by source, confidence, recent runs).
 */
export function useMatchQuality() {
  return useQuery({
    queryKey: ['match-quality'],
    queryFn: () => apiClient.get('/api/admin/match-quality'),
  })
}

/**
 * Fetch matches pending review with optional filters.
 */
export function useMatchReview({ source, limit, offset } = {}) {
  return useQuery({
    queryKey: ['match-review', { source, limit, offset }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (source) params.set('source', source)
      if (limit != null) params.set('limit', String(limit))
      if (offset != null) params.set('offset', String(offset))
      const qs = params.toString()
      return apiClient.get(`/api/admin/match-review${qs ? `?${qs}` : ''}`)
    },
  })
}

/**
 * Trigger scorecard materialized view refresh.
 */
export function useRefreshScorecard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/api/admin/refresh-scorecard'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platform-stats'] })
    },
  })
}

/**
 * Trigger data freshness recalculation.
 */
export function useRefreshFreshness() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/api/admin/refresh-freshness'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['data-freshness'] })
    },
  })
}

/**
 * Approve or reject a match review entry.
 */
export function useReviewMatch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }) =>
      apiClient.post(`/api/admin/match-review/${id}`, { action }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['match-review'] })
    },
  })
}

/**
 * Register a new user account.
 */
export function useRegisterUser() {
  return useMutation({
    mutationFn: ({ username, password, role }) =>
      apiClient.post('/api/auth/register', { username, password, role }),
  })
}
