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

/**
 * Submit a human review for a research fact.
 * POST /api/research/facts/{factId}/review
 */
export function useReviewFact() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ factId, verdict, notes }) =>
      apiClient.post(`/api/research/facts/${factId}/review`, { verdict, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
      queryClient.invalidateQueries({ queryKey: ['review-summary'] })
    },
  })
}

/**
 * Fetch review progress summary for a research run.
 * GET /api/research/runs/{runId}/review-summary
 */
export function useReviewSummary(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['review-summary', runId],
    queryFn: () => apiClient.get(`/api/research/runs/${runId}/review-summary`),
    enabled: enabled && !!runId,
  })
}

/**
 * Set a manual human quality score for a research run.
 * PATCH /api/research/runs/{runId}/human-score
 */
export function useSetHumanScore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, human_quality_score }) =>
      apiClient.patch(`/api/research/runs/${runId}/human-score`, { human_quality_score }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
    },
  })
}

/**
 * Set run-level usefulness (thumbs up/down).
 * PATCH /api/research/runs/{runId}/usefulness
 */
export function useSetRunUsefulness() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, useful }) =>
      apiClient.patch(`/api/research/runs/${runId}/usefulness`, { useful }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
      queryClient.invalidateQueries({ queryKey: ['research-status'] })
    },
  })
}

/**
 * Flag a fact as wrong (shorthand for reject).
 * POST /api/research/facts/{factId}/flag
 */
export function useFlagFact() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ factId }) =>
      apiClient.post(`/api/research/facts/${factId}/flag`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
      queryClient.invalidateQueries({ queryKey: ['review-summary'] })
      queryClient.invalidateQueries({ queryKey: ['priority-facts'] })
    },
  })
}

/**
 * Auto-confirm unflagged facts after run usefulness is set.
 * POST /api/research/maintenance/auto-confirm?run_id={runId}
 */
export function useAutoConfirmFacts() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId }) =>
      apiClient.post(`/api/research/maintenance/auto-confirm?run_id=${runId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
      queryClient.invalidateQueries({ queryKey: ['review-summary'] })
    },
  })
}

/**
 * Review all facts in a dossier section at once.
 * POST /api/research/runs/{runId}/sections/{section}/review
 */
export function useReviewSection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, section, verdict, notes }) =>
      apiClient.post(`/api/research/runs/${runId}/sections/${section}/review`, { verdict, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-result'] })
      queryClient.invalidateQueries({ queryKey: ['review-summary'] })
    },
  })
}

/**
 * Fetch priority facts for active learning prompts.
 * GET /api/research/runs/{runId}/priority-facts
 */
export function usePriorityFacts(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['priority-facts', runId],
    queryFn: () => apiClient.get(`/api/research/runs/${runId}/priority-facts`),
    enabled: enabled && !!runId,
  })
}

/**
 * Fetch comparison data for two runs.
 * GET /api/research/runs/compare?run_a={a}&run_b={b}
 */
export function useCompareRuns(runIdA, runIdB, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['compare-runs', runIdA, runIdB],
    queryFn: () => apiClient.get(`/api/research/runs/compare?run_a=${runIdA}&run_b=${runIdB}`),
    enabled: enabled && !!runIdA && !!runIdB,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Submit A/B comparison verdict.
 * POST /api/research/runs/compare
 */
export function useSubmitComparison() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) =>
      apiClient.post('/api/research/runs/compare', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compare-runs'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Gold Standard Review Hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the gold standard review queue (completed runs with review progress).
 */
export function useGoldReviewQueue({ review_status, q, min_quality, page = 1, limit = 20 } = {}) {
  return useQuery({
    queryKey: ['gold-review-queue', { review_status, q, min_quality, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (review_status) params.set('review_status', review_status)
      if (q) params.set('q', q)
      if (min_quality != null) params.set('min_quality', String(min_quality))
      params.set('page', String(page))
      params.set('limit', String(limit))
      return apiClient.get(`/api/research/review/queue?${params}`)
    },
    placeholderData: (prev) => prev,
  })
}

/**
 * Fetch gold standard review progress stats.
 */
export function useGoldReviewStats() {
  return useQuery({
    queryKey: ['gold-review-stats'],
    queryFn: () => apiClient.get('/api/research/review/stats'),
    staleTime: 30 * 1000,
  })
}

/**
 * Fetch section-level reviews for a run.
 */
export function useSectionReviews(runId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['section-reviews', runId],
    queryFn: () => apiClient.get(`/api/research/runs/${runId}/section-reviews`),
    enabled: enabled && !!runId,
  })
}

/**
 * Submit a gold standard section review.
 */
export function useSubmitSectionReview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, section, review_action, reviewer_notes, corrected_content }) =>
      apiClient.post(`/api/research/runs/${runId}/section-review/${section}`, {
        review_action,
        reviewer_notes: reviewer_notes || null,
        corrected_content: corrected_content || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['section-reviews'] })
      queryClient.invalidateQueries({ queryKey: ['gold-review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['gold-review-stats'] })
    },
  })
}

/**
 * Mark a run as gold standard.
 */
export function useMarkGoldStandard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId }) =>
      apiClient.post(`/api/research/runs/${runId}/gold-standard`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gold-review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['gold-review-stats'] })
      queryClient.invalidateQueries({ queryKey: ['section-reviews'] })
    },
  })
}

/**
 * Remove gold standard designation.
 */
export function useUnmarkGoldStandard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ runId }) =>
      apiClient.delete(`/api/research/runs/${runId}/gold-standard`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gold-review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['gold-review-stats'] })
    },
  })
}
