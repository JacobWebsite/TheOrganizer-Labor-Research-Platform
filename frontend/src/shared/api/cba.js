import { useQuery } from '@tanstack/react-query'
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
