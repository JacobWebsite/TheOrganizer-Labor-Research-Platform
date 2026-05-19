/**
 * NlrbSection polish-sweep tests (Week 4 A.3).
 *
 * Confirms the four standard states render distinctly:
 * - Loading: skeleton placeholder (isLoading=true)
 * - Error: amber retry panel, retry button calls onRetry
 * - Empty: "No records matched" amber panel ("no data")
 * - Partial: per-sub-section empty lines when one of {elections, ULPs} has
 *   data and the other does not. The card shows zero-state notes per
 *   sub-section so users see the gap is intentional.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/shared/components/SourceFreshnessFooter', () => ({
  SourceFreshnessFooter: () => null,
}))

import { NlrbSection } from '@/features/employer-profile/NlrbSection'

function renderCard(props = {}) {
  return render(<NlrbSection {...props} />)
}

describe('NlrbSection states', () => {
  it('renders loading skeleton when isLoading=true', () => {
    const { container } = renderCard({ isLoading: true })
    expect(screen.getByText('NLRB Activity')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="nlrb-card-skeleton"]')).not.toBeNull()
    expect(screen.queryByText(/No NLRB election or unfair/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button calling onRetry', () => {
    const onRetry = vi.fn()
    renderCard({ isError: true, onRetry })
    expect(screen.getByText(/Could not load NLRB election and ULP data/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders empty "no records matched" amber panel when nlrb is missing', () => {
    renderCard({ nlrb: null })
    expect(screen.getByText('No records matched')).toBeInTheDocument()
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(
      screen.getByText(/No NLRB election or unfair labor practice records/),
    ).toBeInTheDocument()
  })

  it('renders partial state: elections present but no ULP cases', () => {
    const nlrb = {
      summary: {
        total_elections: 2,
        union_wins: 1,
        union_losses: 1,
        ulp_cases: 0,
      },
      elections: [
        {
          case_number: '01-RC-1',
          election_date: '2024-03-15',
          union_won: true,
          eligible_voters: 50,
          union_name: 'SEIU',
        },
      ],
      ulp_cases: [],
    }
    renderCard({ nlrb })
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(
      screen.getByText(/No unfair labor practice cases on file/),
    ).toBeInTheDocument()
  })

  it('renders partial state: ULP cases present but no elections', () => {
    const nlrb = {
      summary: {
        total_elections: 0,
        ulp_cases: 1,
      },
      elections: [],
      ulp_cases: [
        {
          case_number: '01-CA-1',
          date_filed: '2024-04-15',
          status: 'Open',
          allegation: '8(a)(1)',
        },
      ],
    }
    renderCard({ nlrb })
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(
      screen.getByText(/No NLRB elections on file/),
    ).toBeInTheDocument()
  })
})
