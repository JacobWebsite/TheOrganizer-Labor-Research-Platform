import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Parse a canonical_id to determine the source type.
 * F7 IDs are plain hex strings. Non-F7 IDs are prefixed: NLRB-123, VR-456, MANUAL-789.
 */
export function parseCanonicalId(id) {
  if (!id) return { isF7: false, sourceType: 'UNKNOWN', rawId: id }

  const prefixMatch = id.match(/^(NLRB|VR|MANUAL)-(.+)$/)
  if (prefixMatch) {
    return { isF7: false, sourceType: prefixMatch[1], rawId: prefixMatch[2] }
  }

  // Plain hex string = F7
  return { isF7: true, sourceType: 'F7', rawId: id }
}

/**
 * Fetch full employer profile (F7 employers only).
 * Returns: { employer, unified_scorecard, osha, nlrb, cross_references, flags }
 */
export function useEmployerProfile(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-profile', id],
    queryFn: () => apiClient.get(`/api/profile/employers/${id}`),
    enabled: enabled && !!id,
  })
}

/**
 * Fetch unified detail for non-F7 employers (NLRB, VR, MANUAL).
 * Returns: { employer, source_type, cross_references, flags }
 */
export function useEmployerUnifiedDetail(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-unified-detail', id],
    queryFn: () => apiClient.get(`/api/employers/unified-detail/${id}`),
    enabled: enabled && !!id,
  })
}

/**
 * Fetch scorecard detail with factor explanations (F7 only).
 * Returns: { ..., explanations: { osha, nlrb, whd, ... } }
 */
export function useScorecardDetail(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['scorecard-detail', id],
    queryFn: () => apiClient.get(`/api/scorecard/unified/${id}`),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes — scorecard data changes infrequently
  })
}
