import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

// Mock admin API hooks
vi.mock('@/shared/api/admin', () => ({
  useMatchReview: vi.fn(() => ({ data: null, isLoading: false })),
  useReviewMatch: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import { useMatchReview, useReviewMatch } from '@/shared/api/admin'
import { MatchReviewCard } from '@/features/admin/MatchReviewCard'

const MOCK_MATCHES = {
  matches: [
    { id: 1, target_id: 'abc123', source_system: 'osha', confidence_score: 0.72, evidence: { target_name: 'Acme Corp', source_name: 'ACME CORPORATION' } },
    { id: 2, target_id: 'def456', source_system: 'sam', confidence_score: 0.68, evidence: { target_name: 'Beta LLC', source_name: 'BETA LLC' } },
  ],
  total: 2,
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MatchReviewCard />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MatchReviewCard', () => {
  let mockMutate

  beforeEach(() => {
    mockMutate = vi.fn()
    useMatchReview.mockReturnValue({ data: null, isLoading: false })
    useReviewMatch.mockReturnValue({ mutate: mockMutate, isPending: false })
  })

  it('renders table with match data', () => {
    useMatchReview.mockReturnValue({ data: MOCK_MATCHES, isLoading: false })
    renderCard()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('ACME CORPORATION')).toBeInTheDocument()
    expect(screen.getByText('Beta LLC')).toBeInTheDocument()
    expect(screen.getByText('BETA LLC')).toBeInTheDocument()
    expect(screen.getByText('0.72')).toBeInTheDocument()
    expect(screen.getByText('0.68')).toBeInTheDocument()
  })

  it('shows approve button that calls mutate with correct args', () => {
    useMatchReview.mockReturnValue({ data: MOCK_MATCHES, isLoading: false })
    renderCard()
    const approveButtons = screen.getAllByText('Approve')
    fireEvent.click(approveButtons[0])
    expect(mockMutate).toHaveBeenCalledWith(
      { id: 1, action: 'approve' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    )
  })

  it('shows reject button that calls mutate with correct args', () => {
    useMatchReview.mockReturnValue({ data: MOCK_MATCHES, isLoading: false })
    renderCard()
    const rejectButtons = screen.getAllByText('Reject')
    fireEvent.click(rejectButtons[0])
    expect(mockMutate).toHaveBeenCalledWith(
      { id: 1, action: 'reject' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    )
  })

  it('shows empty state when no matches', () => {
    useMatchReview.mockReturnValue({ data: { matches: [], total: 0 }, isLoading: false })
    renderCard()
    expect(screen.getByText(/All clear/)).toBeInTheDocument()
  })
})
