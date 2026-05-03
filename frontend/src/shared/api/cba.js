import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export function useCBADocuments({ employer, union, category, date_from, date_to, page = 1, limit = 25, enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-documents', { employer, union, category, date_from, date_to, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (employer) params.set('employer', employer)
      if (union) params.set('union', union)
      if (category) params.set('category', category)
      if (date_from) params.set('date_from', date_from)
      if (date_to) params.set('date_to', date_to)
      params.set('limit', String(limit))
      params.set('offset', String((page - 1) * limit))
      return apiClient.get(`/api/cba/documents?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

export function useCBADocument(cbaId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-document', cbaId],
    queryFn: () => apiClient.get(`/api/cba/documents/${cbaId}?include_provisions=true`),
    enabled: enabled && !!cbaId,
  })
}

export function useCBACategories() {
  return useQuery({
    queryKey: ['cba-categories'],
    queryFn: () => apiClient.get('/api/cba/categories'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCBAFilterOptions() {
  return useQuery({
    queryKey: ['cba-filter-options'],
    queryFn: () => apiClient.get('/api/cba/filter-options'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCBAProvisionSearch({ q, category, provision_class, modal_verb, min_confidence, employer_name, union_name, page = 1, limit = 25, enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-provision-search', { q, category, provision_class, modal_verb, min_confidence, employer_name, union_name, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (category) params.set('category', category)
      if (provision_class) params.set('provision_class', provision_class)
      if (modal_verb) params.set('modal_verb', modal_verb)
      if (min_confidence != null) params.set('min_confidence', String(min_confidence))
      if (employer_name) params.set('employer_name', employer_name)
      if (union_name) params.set('union_name', union_name)
      params.set('page', String(page))
      params.set('limit', String(limit))
      return apiClient.get(`/api/cba/provisions/search?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

export function useCBACompare(cbaIds, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-compare', cbaIds],
    queryFn: () => {
      const params = new URLSearchParams()
      if (cbaIds?.length) params.set('cba_ids', cbaIds.join(','))
      return apiClient.get(`/api/cba/compare?${params}`)
    },
    enabled: enabled && cbaIds?.length >= 2,
  })
}

export function useCBAProvisionClasses() {
  return useQuery({
    queryKey: ['cba-provision-classes'],
    queryFn: () => apiClient.get('/api/cba/provisions/classes'),
    staleTime: Infinity,
  })
}

export function useCBARules() {
  return useQuery({
    queryKey: ['cba-rules'],
    queryFn: () => apiClient.get('/api/cba/rules'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCBAReviewQueue({ category, rule_name, review_status, min_confidence, max_confidence, page = 1, limit = 25, sort, order, enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-review-queue', { category, rule_name, review_status, min_confidence, max_confidence, page, limit, sort, order }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (category) params.set('category', category)
      if (rule_name) params.set('rule_name', rule_name)
      if (review_status) params.set('review_status', review_status)
      if (min_confidence != null) params.set('min_confidence', String(min_confidence))
      if (max_confidence != null) params.set('max_confidence', String(max_confidence))
      if (sort) params.set('sort', sort)
      if (order) params.set('order', order)
      params.set('page', String(page))
      params.set('limit', String(limit))
      return apiClient.get(`/api/cba/review/queue?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

export function useCBAReviewStats() {
  return useQuery({
    queryKey: ['cba-review-stats'],
    queryFn: () => apiClient.get('/api/cba/review/stats'),
    staleTime: 30 * 1000,
  })
}

export function useCBAArticles(cbaId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-articles', cbaId],
    queryFn: () => apiClient.get(`/api/cba/documents/${cbaId}/articles`),
    enabled: enabled && !!cbaId,
  })
}

export function useCBAArticleSearch({ q, category, category_group, employer_name, union_name, sort_by, page = 1, limit = 25, enabled = true } = {}) {
  return useQuery({
    queryKey: ['cba-article-search', { q, category, category_group, employer_name, union_name, sort_by, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (category) params.set('category', category)
      if (category_group) params.set('category_group', category_group)
      if (employer_name) params.set('employer_name', employer_name)
      if (union_name) params.set('union_name', union_name)
      if (sort_by) params.set('sort_by', sort_by)
      params.set('page', String(page))
      params.set('limit', String(limit))
      return apiClient.get(`/api/cba/articles/search?${params}`)
    },
    enabled: enabled && !!(q || category || category_group),
    placeholderData: (prev) => prev,
  })
}

export function useCBACategoryGroups() {
  return useQuery({
    queryKey: ['cba-category-groups'],
    queryFn: () => apiClient.get('/api/cba/category-groups'),
    staleTime: Infinity,
  })
}

export function useCBASemanticSearch({
  q,
  types = 'article,provision',
  top_k = 25,
  min_similarity = 0,
  employer_name,
  union_name,
  category,
  category_group,
  cba_id,
  enabled = true,
} = {}) {
  return useQuery({
    queryKey: ['cba-semantic-search', {
      q, types, top_k, min_similarity,
      employer_name, union_name, category, category_group, cba_id,
    }],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('q', q)
      params.set('types', types)
      params.set('top_k', String(top_k))
      if (min_similarity > 0) params.set('min_similarity', String(min_similarity))
      if (employer_name) params.set('employer_name', employer_name)
      if (union_name) params.set('union_name', union_name)
      if (category) params.set('category', category)
      if (category_group) params.set('category_group', category_group)
      if (cba_id != null) params.set('cba_id', String(cba_id))
      return apiClient.get(`/api/cba/semantic-search?${params}`)
    },
    enabled: enabled && !!q && q.trim().length >= 2,
    placeholderData: (prev) => prev,
    // Semantic search is expensive (Gemini API call), so cache aggressively
    staleTime: 5 * 60 * 1000,
  })
}

export function useSubmitCBAReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ provisionId, review_action, corrected_category, corrected_class, notes }) =>
      apiClient.post(`/api/cba/provisions/${provisionId}/review`, {
        review_action,
        corrected_category: corrected_category || null,
        corrected_class: corrected_class || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cba-review-queue'] })
      qc.invalidateQueries({ queryKey: ['cba-review-stats'] })
      qc.invalidateQueries({ queryKey: ['cba-rules'] })
    },
  })
}
