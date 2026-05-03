import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Parse a canonical_id to determine the source type.
 * F7 IDs are plain hex strings. Non-F7 IDs are prefixed: NLRB-123, VR-456, MANUAL-789, MASTER-123.
 */
export function parseCanonicalId(id) {
  if (!id) return { isF7: false, sourceType: 'UNKNOWN', rawId: id }

  const prefixMatch = id.match(/^(NLRB|VR|MANUAL|MASTER)-(.+)$/)
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

export function useEmployerComparables(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-comparables', id],
    queryFn: () => apiClient.get(`/api/employers/${id}/comparables`),
    enabled: enabled && !!id,
  })
}

export function useEmployerWhd(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-whd', id],
    queryFn: () => apiClient.get(`/api/whd/employer/${id}`),
    enabled: enabled && !!id,
  })
}

// 24Q-31: EPA ECHO environmental enforcement on the master profile.
// Endpoint returns { summary, facilities, latest_record_date }.
export function useMasterEpaEcho(masterId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['master-epa-echo', masterId],
    queryFn: () => apiClient.get(`/api/employers/master/${masterId}/epa-echo`),
    enabled: enabled && !!masterId,
    staleTime: 10 * 60 * 1000,
  })
}

// 24Q-7: Mergent executive roster on the master profile.
// Endpoint returns { summary, executives, source_freshness }.
export function useMasterExecutives(masterId, { enabled = true, limit = 25 } = {}) {
  return useQuery({
    queryKey: ['master-executives', masterId, limit],
    queryFn: () =>
      apiClient.get(`/api/employers/master/${masterId}/executives?limit=${limit}`),
    enabled: enabled && !!masterId,
    staleTime: 10 * 60 * 1000,
  })
}

// 24Q-9: SEC 13F institutional ownership on the master profile.
// Endpoint returns { summary, owners }.
export function useMasterInstitutionalOwners(masterId, { enabled = true, limit = 25 } = {}) {
  return useQuery({
    queryKey: ['master-institutional-owners', masterId, limit],
    queryFn: () =>
      apiClient.get(`/api/employers/master/${masterId}/institutional-owners?limit=${limit}`),
    enabled: enabled && !!masterId,
    staleTime: 10 * 60 * 1000,
  })
}

// 24Q-39: LDA federal lobbying disclosure on the master profile.
// Endpoint returns { summary, quarterly_spend, top_issues, top_registrants }.
export function useMasterLobbying(masterId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['master-lobbying', masterId],
    queryFn: () =>
      apiClient.get(`/api/employers/master/${masterId}/lobbying`),
    enabled: enabled && !!masterId,
    staleTime: 10 * 60 * 1000,
  })
}

export function useEmployerCorporate(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-corporate', id],
    queryFn: () => apiClient.get(`/api/corporate/hierarchy/${id}`),
    enabled: enabled && !!id,
  })
}

export function useEmployerDataSources(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-data-sources', id],
    queryFn: () => apiClient.get(`/api/employers/${id}/data-sources`),
    enabled: enabled && !!id,
  })
}

export function useEmployerFinancials(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-financials', id],
    queryFn: () => apiClient.get(`/api/employers/${id}/financials`),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000,
  })
}

export function useEmployerMatches(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-matches', id],
    queryFn: () => apiClient.get(`/api/employers/${id}/matches`),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000,
  })
}

export function useEmployerFlags(id, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['employer-flags', id],
    queryFn: () => apiClient.get(`/api/employers/flags/by-employer/${id}`),
    enabled: enabled && !!id,
  })
}

export function useEmployerOccupations(employerId) {
  return useQuery({
    queryKey: ['employer-occupations', employerId],
    queryFn: () => apiClient.get(`/api/profile/employers/${employerId}/occupations`),
    enabled: !!employerId,
    staleTime: 10 * 60 * 1000,
  })
}

export function useEmployerWorkplaceDemographics(employerId) {
  return useQuery({
    queryKey: ['workplace-demographics', employerId],
    queryFn: () => apiClient.get(`/api/profile/employers/${employerId}/workplace-demographics`),
    enabled: !!employerId,
    staleTime: 30 * 60 * 1000,
  })
}

export function useEmployerDemographics(state, naics) {
  const enabled = !!state
  const path = naics
    ? `/api/demographics/${state}/${naics}`
    : `/api/demographics/${state}`
  return useQuery({
    queryKey: ['demographics', state, naics],
    queryFn: () => apiClient.get(path),
    enabled,
    staleTime: 30 * 60 * 1000,
  })
}

export function useFlagEmployer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.post('/api/employers/flags', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employer-flags'] })
    },
  })
}

/**
 * Corporate-family rollup for a master_employers row.
 *
 * Aggregates NLRB + OSHA + WHD + F-7 data across all name-variant siblings of
 * the given master_id, using canonical-stem extraction. This solves the
 * "Starbucks has 380 masters but only 2 show direct linkage to the canonical
 * parent" problem by name-matching across all family members.
 *
 * Returns: { family_stem, master_count, masters_by_source, nlrb: {...},
 *           osha: {...}, whd: {...}, f7: {...} }
 *
 * Where nlrb = { totals, elections_summary, elections_by_year, elections_by_state,
 *               recent_elections, allegations_by_section, respondent_variants }
 */
export function useEmployerFamilyRollup(masterId, { enabled = true, limit = 100 } = {}) {
  return useQuery({
    queryKey: ['employer-family-rollup', masterId, limit],
    queryFn: () =>
      apiClient.get(
        `/api/employers/master/${masterId}/family-rollup?limit_recent_elections=${limit}`,
      ),
    enabled: enabled && !!masterId,
    staleTime: 10 * 60 * 1000, // 10 min — corporate hierarchy changes slowly
  })
}

/**
 * Same corporate-family rollup, but keyed on an F-7 employer_id (hex) rather
 * than a master_id. The backend extracts the canonical stem from the F-7
 * `name_standard` and runs identical aggregation. Used when the profile
 * page is rendering an F-7-sourced employer (e.g. one Starbucks store's
 * F-7 row) so that page also gets the full national-family view.
 */
export function useEmployerFamilyRollupForF7(f7Id, { enabled = true, limit = 100 } = {}) {
  return useQuery({
    queryKey: ['employer-family-rollup-f7', f7Id, limit],
    queryFn: () =>
      apiClient.get(
        `/api/employers/f7/${f7Id}/family-rollup?limit_recent_elections=${limit}`,
      ),
    enabled: enabled && !!f7Id,
    staleTime: 10 * 60 * 1000,
  })
}

/**
 * State and local government contracts (NY/VA/OH) matched to a master_id.
 * Returns the row from state_local_contracts_master_matches with vendor name,
 * source tables, match tier, and an amount_caveat field. (R7-9, 2026-04-27)
 *
 * Note: total_contract_amount is unreliable across sources (NY ABO has
 * $1.2Q-class typos). Prefer source_count and contract_row_count for display.
 */
export function useEmployerMasterStateLocalContracts(
  masterId,
  { enabled = true, includeReviewTier = false } = {},
) {
  return useQuery({
    queryKey: ['employer-state-local-contracts', masterId, includeReviewTier],
    queryFn: () =>
      apiClient.get(
        `/api/employers/master/${masterId}/state-local-contracts` +
          (includeReviewTier ? '?include_review_tier=true' : ''),
      ),
    enabled: enabled && !!masterId,
    // 404 = "no state/local matches" — treated by TanStack as an error.
    // Components should handle isError as well as isLoading/data.
    retry: false,
    staleTime: 10 * 60 * 1000,
  })
}
