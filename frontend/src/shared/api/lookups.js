import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

/**
 * Fetch all states with employer counts. Cached for the session.
 */
export function useStates() {
  return useQuery({
    queryKey: ['lookups', 'states'],
    queryFn: () => apiClient.get('/api/lookups/states'),
    staleTime: Infinity,
  })
}

/**
 * Fetch NAICS 2-digit sectors. Cached for the session.
 */
export function useNaicsSectors() {
  return useQuery({
    queryKey: ['lookups', 'naics-sectors'],
    queryFn: () => apiClient.get('/api/lookups/naics-sectors'),
    staleTime: Infinity,
  })
}
