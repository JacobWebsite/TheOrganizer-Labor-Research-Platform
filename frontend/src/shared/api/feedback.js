/**
 * Beta feedback API -- submit tester feedback to /api/feedback.
 */
import { apiClient } from './client'

export function submitFeedback(payload) {
  return apiClient.post('/api/feedback', payload)
}

export function listFeedback({ limit = 100, status } = {}) {
  const params = new URLSearchParams()
  if (limit) params.set('limit', String(limit))
  if (status) params.set('status', status)
  const qs = params.toString()
  return apiClient.get(`/api/feedback${qs ? `?${qs}` : ''}`)
}
