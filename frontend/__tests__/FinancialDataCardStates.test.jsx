/**
 * FinancialDataCard polish-sweep tests (Week 4 A.3).
 *
 * Confirms the four standard states render distinctly:
 * - Loading: skeleton placeholder (isLoading=true)
 * - Error: amber retry panel, retry button calls onRetry
 * - Empty: "No records matched" amber panel ("no data")
 * - Partial: scorecard / industry signals exist but no SEC or 990 detail;
 *   renders an explicit per-section absence note.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/shared/components/SourceFreshnessFooter', () => ({
  SourceFreshnessFooter: () => null,
}))

import { FinancialDataCard } from '@/features/employer-profile/FinancialDataCard'

function renderCard(props = {}) {
  return render(<FinancialDataCard {...props} />)
}

describe('FinancialDataCard states', () => {
  it('renders loading skeleton when isLoading=true', () => {
    const { container } = renderCard({ isLoading: true })
    expect(screen.getByText('Financial Data')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="financial-card-skeleton"]')).not.toBeNull()
    expect(screen.queryByText(/No financial data has been matched/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button calling onRetry', () => {
    const onRetry = vi.fn()
    renderCard({ isError: true, onRetry })
    expect(screen.getByText(/Could not load financial data/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders empty "no records matched" amber panel when no signal exists', () => {
    renderCard({ scorecard: {}, dataSources: {} })
    expect(screen.getByText('No records matched')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Financial Data'))
    expect(
      screen.getByText(/No financial data has been matched/),
    ).toBeInTheDocument()
  })

  it('renders partial-data hint when scorecard signal exists but neither SEC nor 990 detail', () => {
    renderCard({
      scorecard: { bls_growth_pct: 3.5, score_financial: 4.2 },
      dataSources: { is_public: false },
      financials: { has_sec_financials: false, has_990_financials: false },
    })
    fireEvent.click(screen.getByText('Financial Data'))
    expect(
      screen.getByText(/No company-level SEC or IRS 990 financial detail available/),
    ).toBeInTheDocument()
    // industry growth still rendered alongside the partial-data note
    expect(screen.getByText('3.5%')).toBeInTheDocument()
  })
})
