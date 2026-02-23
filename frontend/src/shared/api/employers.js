import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Full employer search with pagination.
 */
export function useEmployerSearch({ name, state, naics, source_type, has_union, limit = 25, offset = 0, enabled = true }) {
  return useQuery({
    queryKey: ['employer-search', { name, state, naics, source_type, has_union, limit, offset }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (name) params.set('name', name)
      if (state) params.set('state', state)
      if (naics) params.set('naics', naics)
      if (source_type) params.set('source_type', source_type)
      if (has_union) params.set('has_union', has_union)
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      return apiClient.get(`/api/employers/unified-search?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev, // keep previous data during pagination
  })
}

/**
 * Autocomplete search (small result set, debounced).
 */
export function useEmployerAutocomplete(query) {
  return useQuery({
    queryKey: ['employer-autocomplete', query],
    queryFn: () => {
      const params = new URLSearchParams({ name: query, limit: '8' })
      return apiClient.get(`/api/employers/unified-search?${params}`)
    },
    enabled: query.length >= 2,
    staleTime: 30_000,
  })
}
