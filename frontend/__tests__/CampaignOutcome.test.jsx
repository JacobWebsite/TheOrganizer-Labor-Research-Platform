import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CampaignOutcomeCard } from '@/features/employer-profile/CampaignOutcomeCard'

vi.mock('@/shared/api/campaigns', () => ({
  useCampaignOutcomes: vi.fn(() => ({ data: { outcomes: [] }, isLoading: false, isError: false })),
  useRecordOutcome: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false })),
}))

import { useCampaignOutcomes, useRecordOutcome } from '@/shared/api/campaigns'

function renderCard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <CampaignOutcomeCard employerId="ABC123" employerName="Acme Logistics" />
    </QueryClientProvider>
  )
}

describe('CampaignOutcomeCard', () => {
  beforeEach(() => {
    useCampaignOutcomes.mockReturnValue({ data: { outcomes: [] }, isLoading: false, isError: false })
    useRecordOutcome.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false })
  })

  it('renders with no outcomes', () => {
    renderCard()
    fireEvent.click(screen.getByText('Campaign Outcomes'))
    expect(screen.getByText(/No outcomes recorded yet/i)).toBeInTheDocument()
  })

  it('renders existing outcomes', () => {
    useCampaignOutcomes.mockReturnValue({
      data: {
        outcomes: [
          { id: 1, outcome: 'won', notes: 'Unit won after card check.', reported_by: 'Maria', outcome_date: '2026-03-01' },
        ],
      },
      isLoading: false,
      isError: false,
    })
    renderCard()
    fireEvent.click(screen.getByText('Campaign Outcomes'))
    expect(screen.getByText('Won')).toBeInTheDocument()
    expect(screen.getByText(/Unit won after card check/i)).toBeInTheDocument()
  })

  it('opens and submits the form', () => {
    const mutate = vi.fn()
    useRecordOutcome.mockReturnValue({ mutate, isPending: false, isError: false })
    renderCard()
    fireEvent.click(screen.getByText('Campaign Outcomes'))
    fireEvent.click(screen.getByText('Record Outcome'))
    fireEvent.change(screen.getByLabelText('Outcome'), { target: { value: 'lost' } })
    fireEvent.change(screen.getByLabelText('Reported By'), { target: { value: 'Alex' } })
    fireEvent.change(screen.getByLabelText('Outcome Date'), { target: { value: '2026-03-05' } })
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'Campaign paused after election loss.' } })
    fireEvent.click(screen.getByText('Save Outcome'))

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        employer_id: 'ABC123',
        employer_name: 'Acme Logistics',
        outcome: 'lost',
        reported_by: 'Alex',
        outcome_date: '2026-03-05',
      }),
      expect.any(Object),
    )
  })
})
