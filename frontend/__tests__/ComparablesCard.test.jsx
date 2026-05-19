/**
 * ComparablesCard tests.
 *
 * Covers:
 * - Loading: skeleton placeholder (Week 4 A.3 polish-sweep upgrade)
 * - Error: amber retry panel, retry button calls refetch (Week 4 A.3)
 * - Empty: "no comparables found" copy with explanation (Week 4 A.3)
 * - 2026-04-24 fix: backend `comparable_type` (not legacy `union_name`)
 *   drives the unionized header chip and per-row Union/Non-union badge.
 *
 * Critical UX distinction (CLAUDE.md): "no data" must be visibly distinct
 * from "no violations / no matches". The empty state below renders an
 * explicit panel rather than returning null so users see the card is
 * intentionally empty, not hidden.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ComparablesCard } from '@/features/employer-profile/ComparablesCard'

vi.mock('@/shared/api/profile', () => ({
  useEmployerComparables: vi.fn(),
}))

import { useEmployerComparables } from '@/shared/api/profile'

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('ComparablesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: true,
      isError: false,
      data: null,
      refetch: vi.fn(),
    })
    const { container } = renderWithRouter(<ComparablesCard employerId="abc" />)
    // Card title visible
    expect(screen.getByText('Comparable Employers')).toBeInTheDocument()
    // Skeleton testid present (loading state opens by default via defaultOpen)
    expect(container.querySelector('[data-testid="comparables-card-skeleton"]')).not.toBeNull()
    // Should not show empty/error copy
    expect(screen.queryByText(/No comparable employers were found/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Could not load comparable employers/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button that calls refetch', () => {
    const refetch = vi.fn()
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: true,
      data: null,
      refetch,
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    expect(screen.getByText(/Could not load comparable employers/)).toBeInTheDocument()
    const retryBtn = screen.getByRole('button', { name: /retry/i })
    fireEvent.click(retryBtn)
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('renders empty state with "no data" explanation when comparables array is empty', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { employer_id: 'abc', comparables: [] },
      refetch: vi.fn(),
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Header summary
    expect(screen.getByText(/No comparables found/)).toBeInTheDocument()
    // Body copy hidden until expanded; click to reveal
    fireEvent.click(screen.getByText('Comparable Employers'))
    expect(
      screen.getByText(/No comparable employers were found/),
    ).toBeInTheDocument()
  })

  it('renders empty state when data is missing entirely', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: false,
      data: null,
      refetch: vi.fn(),
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    expect(screen.getByText(/No comparables found/)).toBeInTheDocument()
  })

  it('counts unionized correctly from comparable_type (not legacy union_name)', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        employer_id: 'abc',
        comparables: [
          {
            rank: 1,
            comparable_id: '1001',
            comparable_name: 'Acme Union Shop',
            comparable_type: 'union',
            similarity_pct: 95,
            match_reasons: ['NAICS', 'state'],
          },
          {
            rank: 2,
            comparable_id: '1002',
            comparable_name: 'Beta Union Shop',
            comparable_type: 'union',
            similarity_pct: 90,
            match_reasons: [],
          },
          {
            rank: 3,
            comparable_id: '1003',
            comparable_name: 'Gamma Non-Union',
            comparable_type: 'non_union',
            similarity_pct: 85,
            match_reasons: [],
          },
        ],
      },
      refetch: vi.fn(),
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Header summary should say "2 unionized" (not 0)
    expect(screen.getByText(/3 comparable employers · 2 unionized/)).toBeInTheDocument()
  })

  it('renders Union / Non-union labels in expanded body based on comparable_type', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        employer_id: 'abc',
        comparables: [
          {
            rank: 1,
            comparable_id: '1001',
            comparable_name: 'A',
            comparable_type: 'union',
            similarity_pct: 95,
            match_reasons: [],
          },
          {
            rank: 2,
            comparable_id: '1002',
            comparable_name: 'B',
            comparable_type: 'non_union',
            similarity_pct: 90,
            match_reasons: [],
          },
        ],
      },
      refetch: vi.fn(),
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Expand the collapsible so table rows are in DOM
    fireEvent.click(screen.getByText('Comparable Employers'))
    expect(screen.getByText('Union')).toBeInTheDocument()
    expect(screen.getByText('Non-union')).toBeInTheDocument()
  })

  it('falls back to "--" when comparable_type is missing', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        employer_id: 'abc',
        comparables: [
          {
            rank: 1,
            comparable_id: '1001',
            comparable_name: 'Unknown',
            comparable_type: null,
            similarity_pct: 80,
            match_reasons: [],
          },
        ],
      },
      refetch: vi.fn(),
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Header chip (always visible) should say "0 unionized"
    expect(screen.getByText(/1 comparable employers · 0 unionized/)).toBeInTheDocument()
    // Expand to check the fallback '--'
    fireEvent.click(screen.getByText('Comparable Employers'))
    expect(screen.getByText('--')).toBeInTheDocument()
  })
})
