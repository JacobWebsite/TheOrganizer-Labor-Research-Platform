import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export function useCampaignOutcomes(employerId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['campaign-outcomes', employerId],
    queryFn: () => apiClient.get(`/api/campaigns/outcomes/${employerId}`),
    enabled: enabled && !!employerId,
  })
}

export function useRecordOutcome() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.post('/api/campaigns/outcomes', data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['campaign-outcomes', variables.employer_id] })
    },
  })
}
