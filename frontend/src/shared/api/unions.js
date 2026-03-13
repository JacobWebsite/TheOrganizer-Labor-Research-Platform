import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Search unions with filters and server-side pagination.
 */
export function useUnionSearch({
  name, aff_abbr, sector, state, min_members, has_employers,
  page = 1, limit = 50, enabled = true,
} = {}) {
  return useQuery({
    queryKey: ['union-search', { name, aff_abbr, sector, state, min_members, has_employers, page, limit }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (name) params.set('name', name)
      if (aff_abbr) params.set('aff_abbr', aff_abbr)
      if (sector) params.set('sector', sector)
      if (state) params.set('state', state)
      if (min_members != null) params.set('min_members', String(min_members))
      if (has_employers != null) params.set('has_employers', String(has_employers))
      params.set('limit', String(limit))
      params.set('offset', String((page - 1) * limit))
      return apiClient.get(`/api/unions/search?${params}`)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}

/**
 * Fetch top national affiliations with member/local counts.
 */
export function useNationalUnions() {
  return useQuery({
    queryKey: ['national-unions'],
    queryFn: () => apiClient.get('/api/unions/national'),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Fetch full union detail by f_num.
 */
export function useUnionDetail(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-detail', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}`),
    enabled: enabled && !!fnum,
  })
}

/**
 * Fetch employers list for a union.
 */
export function useUnionEmployers(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-employers', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}/employers`),
    enabled: enabled && !!fnum,
  })
}

/**
 * Fetch organizing capacity metrics for a union.
 */
export function useUnionOrganizingCapacity(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-organizing-capacity', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}/organizing-capacity`),
    enabled: enabled && !!fnum,
  })
}

/**
 * Fetch 10-year membership history with trend metrics.
 */
export function useUnionMembershipHistory(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-membership-history', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}/membership-history`),
    enabled: enabled && !!fnum,
  })
}

/**
 * Fetch categorized disbursement breakdown for a union.
 */
export function useUnionDisbursements(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-disbursements', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}/disbursements`),
    enabled: enabled && !!fnum,
  })
}

/**
 * Fetch union sector lookup values.
 */
export function useUnionSectors() {
  return useQuery({
    queryKey: ['lookups', 'union-sectors'],
    queryFn: () => apiClient.get('/api/lookups/sectors'),
    staleTime: Infinity,
  })
}

/**
 * Fetch national affiliations with stats.
 */
export function useUnionAffiliations() {
  return useQuery({
    queryKey: ['lookups', 'affiliations'],
    queryFn: () => apiClient.get('/api/lookups/affiliations'),
    staleTime: Infinity,
  })
}

/**
 * Fetch national union detail by affiliation abbreviation.
 */
export function useNationalUnionDetail(affAbbr, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['national-union-detail', affAbbr],
    queryFn: () => apiClient.get(`/api/unions/national/${affAbbr}`),
    enabled: enabled && !!affAbbr,
  })
}

/**
 * Fetch composite health indicators for a union.
 */
export function useUnionHealth(fnum, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-health', fnum],
    queryFn: () => apiClient.get(`/api/unions/${fnum}/health`),
    enabled: enabled && !!fnum,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Fetch union hierarchy with intermediates for an affiliation.
 */
export function useUnionHierarchy(affAbbr, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['union-hierarchy', affAbbr],
    queryFn: () => apiClient.get(`/api/unions/hierarchy/${affAbbr}`),
    enabled: enabled && !!affAbbr,
  })
}
