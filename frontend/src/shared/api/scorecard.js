import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Fetch unified scorecard employers with filters and pagination.
 */
export function useUnifiedScorecard({
  state, naics, min_score, min_factors, score_tier,
  has_osha, has_nlrb, has_research, has_compound_enforcement,
  sort = 'score', offset = 0, page_size = 50,
  enabled = true,
} = {}) {
  return useQuery({
    queryKey: ['unified-scorecard', { state, naics, min_score, min_factors, score_tier, has_osha, has_nlrb, has_research, has_compound_enforcement, sort, offset, page_size }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (state) params.set('state', state)
      if (naics) params.set('naics', naics)
      if (min_score != null && min_score > 0) params.set('min_score', String(min_score))
      if (min_factors != null) params.set('min_factors', String(min_factors))
      if (score_tier) params.set('score_tier', score_tier)
      if (has_osha != null) params.set('has_osha', String(has_osha))
      if (has_nlrb != null) params.set('has_nlrb', String(has_nlrb))
      if (has_research != null) params.set('has_research', String(has_research))
      if (has_compound_enforcement != null) params.set('has_compound_enforcement', String(has_compound_enforcement))
      params.set('sort', sort)
      params.set('offset', String(offset))
      params.set('page_size', String(page_size))
      return apiClient.get(`/api/scorecard/unified?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

/**
 * Fetch unified scorecard stats overview.
 */
export function useUnifiedScorecardStats() {
  return useQuery({
    queryKey: ['unified-scorecard-stats'],
    queryFn: () => apiClient.get('/api/scorecard/unified/stats'),
    staleTime: 15 * 60 * 1000,
  })
}

/**
 * Fetch unified scorecard state list with counts.
 */
export function useUnifiedScorecardStates() {
  return useQuery({
    queryKey: ['unified-scorecard-states'],
    queryFn: () => apiClient.get('/api/scorecard/unified/states'),
    staleTime: 15 * 60 * 1000,
  })
}

/**
 * Build URL for unified scorecard CSV export with current filters.
 */
export function buildExportUrl({ state, naics, min_score, min_factors, score_tier, has_osha, has_nlrb, has_research, has_compound_enforcement } = {}) {
  const params = new URLSearchParams()
  if (state) params.set('state', state)
  if (naics) params.set('naics', naics)
  if (min_score != null && min_score > 0) params.set('min_score', String(min_score))
  if (min_factors != null) params.set('min_factors', String(min_factors))
  if (score_tier) params.set('score_tier', score_tier)
  if (has_osha != null) params.set('has_osha', String(has_osha))
  if (has_nlrb != null) params.set('has_nlrb', String(has_nlrb))
  if (has_research != null) params.set('has_research', String(has_research))
  if (has_compound_enforcement != null) params.set('has_compound_enforcement', String(has_compound_enforcement))
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8001'
  return `${base}/api/scorecard/unified/export?${params}`
}
