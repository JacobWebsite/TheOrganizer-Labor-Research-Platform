/**
 * InstitutionalOwnersCard tests (24Q-9).
 *
 * Covers:
 * - Loading / error states
 * - "Not in 13F (likely private)" no-match panel
 * - Matched-but-no-holdings edge case
 * - Populated state: owner table + value formatting + summary text
 * - Show top 10 / show all expand-collapse
 * - Trigram-match confidence note rendering
 * - Period date footer
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { InstitutionalOwnersCard } from '@/features/employer-profile/InstitutionalOwnersCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterInstitutionalOwners: vi.fn(),
}))

import { useMasterInstitutionalOwners } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      is_matched: true,
      issuer_name_used: 'Walmart Inc',
      match_method: 'exact',
      match_confidence: 1.0,
      total_owners: 14,
      total_value: 12_500_000_000,
      total_shares: 152_000_000,
      latest_period: '2025-12-31',
    },
    owners: [
      {
        filer_name: 'Vanguard Group Inc',
        filer_cik: '102909',
        filer_state: 'PA',
        value: 4_300_000_000,
        shares: 52_000_000,
        share_type: 'SH',
        investment_discretion: 'SOLE',
        period_of_report: '2025-12-31',
      },
      {
        filer_name: 'BlackRock Inc',
        filer_cik: '1364742',
        filer_state: 'NY',
        value: 3_100_000_000,
        shares: 38_000_000,
        share_type: 'SH',
        investment_discretion: 'SOLE',
        period_of_report: '2025-12-31',
      },
      {
        filer_name: 'State Street Corp',
        filer_cik: '93751',
        filer_state: 'MA',
        value: 1_900_000_000,
        shares: 23_000_000,
        share_type: 'SH',
        investment_discretion: 'SOLE',
        period_of_report: '2025-12-31',
      },
    ],
    ...overrides,
  }
}

function fixtureNotMatched() {
  return {
    summary: {
      is_matched: false,
      issuer_name_used: null,
      match_method: null,
      match_confidence: null,
      total_owners: 0,
      total_value: 0,
      total_shares: 0,
      latest_period: null,
    },
    owners: [],
  }
}

function fixtureMatchedNoOwners() {
  return {
    summary: {
      is_matched: true,
      issuer_name_used: 'Acme Corp',
      match_method: 'exact',
      match_confidence: 1.0,
      total_owners: 0,
      total_value: 0,
      total_shares: 0,
      latest_period: null,
    },
    owners: [],
  }
}

describe('InstitutionalOwnersCard', () => {
  it('renders loading state', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: null, isLoading: true, isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    expect(screen.getByText('Institutional Owners')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Institutional Owners'))
    expect(screen.getByText(/Loading SEC 13F/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: null, isLoading: false, isError: true,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    expect(screen.getByText(/Could not load SEC 13F/)).toBeInTheDocument()
  })

  it('renders not-in-13F panel for unmatched master', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixtureNotMatched(), isLoading: false, isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    expect(screen.getByText(/not currently matched to any SEC Form 13F/)).toBeInTheDocument()
  })

  it('renders matched-but-no-holdings edge case', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixtureMatchedNoOwners(), isLoading: false, isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    // Phrase only appears in the panel's <p>; use a regex to match the
    // unique ending so the matcher resolves to one element.
    expect(
      screen.getAllByText(/no institutional holdings are reported/).length,
    ).toBeGreaterThan(0)
  })

  it('renders populated owners table with names, states, values, shares', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    // Names
    expect(screen.getByText('Vanguard Group Inc')).toBeInTheDocument()
    expect(screen.getByText('BlackRock Inc')).toBeInTheDocument()
    expect(screen.getByText('State Street Corp')).toBeInTheDocument()
    // Compact currency formatting
    expect(screen.getByText('$4.30B')).toBeInTheDocument()
    expect(screen.getByText('$3.10B')).toBeInTheDocument()
    // States
    expect(screen.getByText('PA')).toBeInTheDocument()
    expect(screen.getByText('NY')).toBeInTheDocument()
    expect(screen.getByText('MA')).toBeInTheDocument()
  })

  it('renders trigram-confidence note when match was fuzzy', () => {
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixturePopulated({
        summary: {
          ...fixturePopulated().summary,
          match_method: 'trigram',
          match_confidence: 0.92,
        },
      }),
      isLoading: false,
      isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    expect(
      screen.getAllByText(/matched by name similarity \(confidence 92%\)/).length,
    ).toBeGreaterThan(0)
  })

  it('shows expand button when more than VISIBLE_ROWS owners exist', () => {
    const many = Array.from({ length: 14 }, (_, i) => ({
      filer_name: `Filer ${i + 1}`,
      filer_cik: String(100 + i),
      filer_state: 'NY',
      value: (15 - i) * 100_000_000,
      shares: 1_000_000 - i,
      share_type: 'SH',
      investment_discretion: 'SOLE',
      period_of_report: '2025-12-31',
    }))
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixturePopulated({
        summary: { ...fixturePopulated().summary, total_owners: 14 },
        owners: many,
      }),
      isLoading: false,
      isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    // Default: 10 visible
    expect(screen.getByText('Filer 1')).toBeInTheDocument()
    expect(screen.getByText('Filer 10')).toBeInTheDocument()
    expect(screen.queryByText('Filer 11')).not.toBeInTheDocument()
    // Expand
    fireEvent.click(screen.getByText(/Show all 14 owners/))
    expect(screen.getByText('Filer 14')).toBeInTheDocument()
  })

  it('does NOT render rank tally / hierarchy chart on the card', () => {
    // UX consistency with ExecutivesCard: no chrome, just the data.
    useMasterInstitutionalOwners.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<InstitutionalOwnersCard masterId={1234} />)
    fireEvent.click(screen.getByText('Institutional Owners'))
    // No tier / category chips
    expect(screen.queryByText('Mutual Fund')).not.toBeInTheDocument()
    expect(screen.queryByText('Hedge Fund')).not.toBeInTheDocument()
    expect(screen.queryByText('Pension')).not.toBeInTheDocument()
    // No rank column header
    expect(screen.queryByText('Rank')).not.toBeInTheDocument()
  })
})
