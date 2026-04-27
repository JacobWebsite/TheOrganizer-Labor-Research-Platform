/**
 * ComparablesCard tests -- locks down the 2026-04-24 fix for the
 * `union_name` -> `comparable_type` field drift.
 *
 * Before the fix: backend returned `comparable_type` (value 'union' /
 * 'non_union') but the card read `c.union_name`, causing the header to
 * always say "0 unionized" and the Union column to always show '--'
 * regardless of the comparable's actual status.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ComparablesCard } from '@/features/employer-profile/ComparablesCard'

// Mock the TanStack Query hook so we can inject fixture data without
// hitting the API.
vi.mock('@/shared/api/profile', () => ({
  useEmployerComparables: vi.fn(),
}))

import { useEmployerComparables } from '@/shared/api/profile'

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('ComparablesCard', () => {
  it('returns null when loading', () => {
    useEmployerComparables.mockReturnValue({ isLoading: true, data: null })
    const { container } = renderWithRouter(<ComparablesCard employerId="abc" />)
    expect(container.innerHTML).toBe('')
  })

  it('returns null when comparables array is empty', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
      data: { employer_id: 'abc', comparables: [] },
    })
    const { container } = renderWithRouter(<ComparablesCard employerId="abc" />)
    expect(container.innerHTML).toBe('')
  })

  it('counts unionized correctly from comparable_type (not legacy union_name)', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
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
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Header summary should say "2 unionized" (not 0)
    expect(screen.getByText(/3 comparable employers · 2 unionized/)).toBeInTheDocument()
  })

  it('renders Union / Non-union labels in expanded body based on comparable_type', () => {
    useEmployerComparables.mockReturnValue({
      isLoading: false,
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
    })
    renderWithRouter(<ComparablesCard employerId="abc" />)
    // Header chip (always visible) should say "0 unionized"
    expect(screen.getByText(/1 comparable employers · 0 unionized/)).toBeInTheDocument()
    // Expand to check the fallback '--'
    fireEvent.click(screen.getByText('Comparable Employers'))
    expect(screen.getByText('--')).toBeInTheDocument()
  })
})
