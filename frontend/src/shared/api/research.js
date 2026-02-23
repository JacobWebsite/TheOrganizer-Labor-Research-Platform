import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Start a new research deep dive.
 * POST /api/research/run
 */
export function useStartResearch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.post('/api/research/run', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-runs'] })
    },
  })
}

/**
 * Poll research run status (progress bar, current step).
 * Polls every 2s while pending/running, stops when completed/failed.
 */
export function useResearchStatus(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['research-status', runId],
    queryFn: () => apiClient.get(`/api/research/status/${runId}`),
    enabled: enabled && !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed') return false
      return 2000
    },
  })
}

/**
 * Fetch completed research result (dossier + facts + action log).
 * Results are immutable once completed, so staleTime is long.
 */
export function useResearchResult(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['research-result', runId],
    queryFn: () => apiClient.get(`/api/research/result/${runId}`),
    enabled: enabled && !!runId,
    staleTime: 30 * 60 * 1000, // 30 minutes
  })
}

/**
 * List past research runs with filters and pagination.
 */
export function useResearchRuns({ status, q, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  params.set('offset', String(offset))

  return useQuery({
    queryKey: ['research-runs', { status, q, limit, offset }],
    queryFn: () => apiClient.get(`/api/research/runs?${params}`),
    placeholderData: (prev) => prev,
  })
}

/**
 * Fetch research fact vocabulary (attribute dictionary).
 * Cached for 1 hour since it rarely changes.
 */
export function useResearchVocabulary() {
  return useQuery({
    queryKey: ['research-vocabulary'],
    queryFn: () => apiClient.get('/api/research/vocabulary'),
    staleTime: 60 * 60 * 1000, // 1 hour
  })
}
