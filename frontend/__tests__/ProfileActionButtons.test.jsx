import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { ProfileActionButtons } from '@/features/employer-profile/ProfileActionButtons'

vi.mock('@/shared/api/research', () => ({
  useStartResearch: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useResearchStatus: vi.fn(() => ({ data: null })),
}))

function renderButtons(employer = { employer_id: 'E1', employer_name: 'Test Corp' }, scorecard = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ProfileActionButtons employer={employer} scorecard={scorecard} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ProfileActionButtons', () => {
  it('renders export button', () => {
    renderButtons()
    expect(screen.getByText('Export Data')).toBeInTheDocument()
  })

  it('renders print button', () => {
    renderButtons()
    expect(screen.getByText('Print Profile')).toBeInTheDocument()
  })
})
