/**
 * WhdCard polish-sweep tests (Week 4 A.3).
 *
 * Confirms the four standard states render distinctly:
 * - Loading: skeleton placeholder, no error chrome
 * - Error: amber retry panel, retry button calls refetch
 * - Empty: "No records matched" amber panel with "no data" copy
 * - Partial: aggregate summary present but per-case detail missing
 *
 * Critical UX distinction (CLAUDE.md): "no data" vs "no violations" must look
 * different. The empty state is "no data". A populated state with cases is
 * "no violations" only when totals are zero -- WHD tends to surface cases as
 * the dominant evidence, so the empty/populated split here covers both.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

vi.mock('@/shared/api/profile', () => ({
  useEmployerWhd: vi.fn(),
}))

vi.mock('@/shared/components/SourceFreshnessFooter', () => ({
  SourceFreshnessFooter: () => null,
}))

import { WhdCard } from '@/features/employer-profile/WhdCard'
import { useEmployerWhd } from '@/shared/api/profile'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WhdCard states', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton', () => {
    useEmployerWhd.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    })
    const { container } = renderWithProviders(<WhdCard employerId="abc123" />)
    expect(screen.getByText('Wage & Hour (WHD)')).toBeInTheDocument()
    // Skeleton testid present even before opening (the loading state opens by
    // default via defaultOpen).
    expect(container.querySelector('[data-testid="whd-card-skeleton"]')).not.toBeNull()
    // Should not show the empty-state copy or error copy
    expect(screen.queryByText(/No Wage & Hour Division records/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Could not load Wage & Hour data/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button that calls refetch', () => {
    const refetch = vi.fn()
    useEmployerWhd.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      refetch,
    })
    renderWithProviders(<WhdCard employerId="abc123" />)
    expect(screen.getByText(/Could not load Wage & Hour data/)).toBeInTheDocument()
    const retryBtn = screen.getByRole('button', { name: /retry/i })
    fireEvent.click(retryBtn)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('renders empty state with "no data does not mean no violations" copy', () => {
    useEmployerWhd.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    renderWithProviders(<WhdCard employerId="abc123" />)
    expect(screen.getByText('No records matched')).toBeInTheDocument()
    // CollapsibleCard hides body until expanded; click title to reveal body.
    fireEvent.click(screen.getByText('Wage & Hour (WHD)'))
    expect(
      screen.getByText(/No Wage & Hour Division records have been matched/),
    ).toBeInTheDocument()
  })

  it('renders partial state when summary aggregates exist but cases array is empty', () => {
    useEmployerWhd.mockReturnValue({
      data: {
        whd_summary: {
          whd_violation_count: 5,
          whd_backwages: 12000,
          whd_penalties: 0,
        },
        cases: [],
        latest_record_date: '2024-01-15',
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    renderWithProviders(<WhdCard employerId="abc123" />)
    fireEvent.click(screen.getByText('Wage & Hour (WHD)'))
    expect(
      screen.getByText(/Aggregate WHD totals are available but per-case detail/),
    ).toBeInTheDocument()
  })
})
