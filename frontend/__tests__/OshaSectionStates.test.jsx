/**
 * OshaSection polish-sweep tests (Week 4 A.3).
 *
 * Confirms the four standard states render distinctly:
 * - Loading: skeleton placeholder (passes loading=true)
 * - Error: amber retry panel, retry button calls onRetry
 * - Empty: "No records matched" amber panel ("no data")
 * - Partial / "no violations": establishment matched but zero violations on
 *   file; renders a positive-signal panel that is visibly distinct from the
 *   "no records matched" amber empty state.
 *
 * The "no data" vs "no violations" UX distinction (CLAUDE.md) is exercised
 * directly: empty state uses amber chrome, "no violations" partial uses
 * emerald chrome, and the assertions check for visibly different text.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/shared/components/SourceFreshnessFooter', () => ({
  SourceFreshnessFooter: () => null,
}))

import { OshaSection } from '@/features/employer-profile/OshaSection'

function renderCard(props = {}) {
  return render(<OshaSection {...props} />)
}

describe('OshaSection states', () => {
  it('renders loading skeleton when isLoading=true', () => {
    const { container } = renderCard({ isLoading: true })
    expect(screen.getByText('OSHA Safety Record')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="osha-card-skeleton"]')).not.toBeNull()
    expect(screen.queryByText(/No OSHA records have been matched/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button calling onRetry', () => {
    const onRetry = vi.fn()
    renderCard({ isError: true, onRetry })
    expect(screen.getByText(/Could not load OSHA inspection data/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders empty "no records matched" amber panel when osha is missing', () => {
    renderCard({ osha: null })
    expect(screen.getByText('No records matched')).toBeInTheDocument()
    fireEvent.click(screen.getByText('OSHA Safety Record'))
    expect(
      screen.getByText(/No OSHA records have been matched/),
    ).toBeInTheDocument()
  })

  it('renders partial "no violations" emerald panel when establishments matched but zero violations', () => {
    const osha = {
      summary: {
        total_establishments: 2,
        total_inspections: 0,
        total_violations: 0,
        total_penalties: 0,
      },
      establishments: [
        { establishment_id: 'A', establishment_name: 'Plant A', city: 'X', state: 'OH' },
        { establishment_id: 'B', establishment_name: 'Plant B', city: 'Y', state: 'OH' },
      ],
      latest_record_date: '2024-06-15',
    }
    renderCard({ osha })
    fireEvent.click(screen.getByText('OSHA Safety Record'))
    expect(
      screen.getByText(/No OSHA violations on file/),
    ).toBeInTheDocument()
    // Critical: this is the "no violations" path, NOT the "no data" path.
    expect(
      screen.queryByText(/No OSHA records have been matched/),
    ).not.toBeInTheDocument()
  })
})
