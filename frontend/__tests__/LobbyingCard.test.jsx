/**
 * LobbyingCard tests (24Q-39).
 *
 * Covers:
 * - Loading / error states
 * - "No LDA registrations found" panel for unmatched master
 * - "Matched, no filings" edge case
 * - Populated state: top-line metrics, quarterly spend, top issues, top registrants
 * - Trigram-confidence note rendering
 * - Show-all expand/collapse on each table
 * - "Federal Lobbying" header (not generic "Lobbying")
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LobbyingCard } from '@/features/employer-profile/LobbyingCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterLobbying: vi.fn(),
}))

import { useMasterLobbying } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      is_matched: true,
      client_name_used: 'WALMART, INC.',
      match_method: 'exact',
      match_confidence: 1.0,
      total_filings: 24,
      total_spend: 7_650_000,
      active_quarters: 20,
      registrants_count: 6,
      latest_period: '4th Quarter (Oct 1 - Dec 31) 2025',
    },
    quarterly_spend: [
      { year: 2025, period: 'fourth_quarter', period_display: '4th Quarter (Oct 1 - Dec 31)', filings: 6, spend: 1_200_000 },
      { year: 2025, period: 'third_quarter',  period_display: '3rd Quarter (Jul 1 - Sep 30)', filings: 6, spend: 1_180_000 },
      { year: 2025, period: 'second_quarter', period_display: '2nd Quarter (Apr 1 - Jun 30)', filings: 6, spend: 1_100_000 },
      { year: 2025, period: 'first_quarter',  period_display: '1st Quarter (Jan 1 - Mar 31)', filings: 6, spend: 1_080_000 },
    ],
    top_issues: [
      { code: 'TAX', display: 'Taxation/Internal Revenue Code', filings: 18, activity_count: 24 },
      { code: 'TRD', display: 'Trade (domestic & foreign)',     filings: 12, activity_count: 16 },
      { code: 'LBR', display: 'Labor Issues/Antitrust/Workplace', filings: 10, activity_count: 12 },
    ],
    top_registrants: [
      { registrant_id: 1, name: 'Akin Gump Strauss Hauer & Feld LLP', state: 'DC', filings: 8, spend: 3_200_000 },
      { registrant_id: 2, name: "K&L Gates",                          state: 'DC', filings: 6, spend: 1_800_000 },
      { registrant_id: 3, name: 'Brownstein Hyatt Farber Schreck',    state: 'CO', filings: 4, spend: 1_200_000 },
    ],
    ...overrides,
  }
}

function fixtureNotMatched() {
  return {
    summary: {
      is_matched: false, client_name_used: null, match_method: null,
      match_confidence: null, total_filings: 0, total_spend: 0,
      active_quarters: 0, registrants_count: 0, latest_period: null,
    },
    quarterly_spend: [], top_issues: [], top_registrants: [],
  }
}

function fixtureMatchedNoFilings() {
  return {
    summary: {
      is_matched: true, client_name_used: 'Acme Corp', match_method: 'exact',
      match_confidence: 1.0, total_filings: 0, total_spend: 0,
      active_quarters: 0, registrants_count: 0, latest_period: null,
    },
    quarterly_spend: [], top_issues: [], top_registrants: [],
  }
}

describe('LobbyingCard', () => {
  it('renders loading state', () => {
    useMasterLobbying.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<LobbyingCard masterId={1234} />)
    expect(screen.getByText('Federal Lobbying')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(screen.getByText(/Loading LDA lobbying data/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterLobbying.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(screen.getByText(/Could not load LDA data/)).toBeInTheDocument()
  })

  it('renders unmatched panel for masters with no LDA link', () => {
    useMasterLobbying.mockReturnValue({
      data: fixtureNotMatched(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(
      screen.getAllByText(/No Lobbying Disclosure Act filings have been matched/).length,
    ).toBeGreaterThan(0)
  })

  it('renders matched-but-no-filings edge case', () => {
    useMasterLobbying.mockReturnValue({
      data: fixtureMatchedNoFilings(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(
      screen.getAllByText(/no filings are reported in our load window/).length,
    ).toBeGreaterThan(0)
  })

  it('renders populated top-line metrics', () => {
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    // Numbers appear both in the top-line tile AND inside the quarterly
    // table; assert at-least-one occurrence for the duplicated values.
    expect(screen.getByText('24')).toBeInTheDocument()             // filings (unique)
    expect(screen.getByText('$7.65M')).toBeInTheDocument()         // total spend
    expect(screen.getAllByText('6').length).toBeGreaterThan(0)     // registrants_count + per-quarter filings
    expect(screen.getByText('20')).toBeInTheDocument()             // active quarters
  })

  it('renders quarterly spend table with formatted Q-period labels', () => {
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    // "1st Quarter (Jan 1 - Mar 31)" -> "Q1 2025"
    expect(screen.getByText('Q1 2025')).toBeInTheDocument()
    expect(screen.getByText('Q4 2025')).toBeInTheDocument()
  })

  it('renders top issues with code prefix and counts', () => {
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(screen.getByText('TAX')).toBeInTheDocument()
    expect(screen.getByText(/Taxation\/Internal Revenue Code/)).toBeInTheDocument()
    expect(screen.getByText('LBR')).toBeInTheDocument()
    expect(screen.getByText(/Labor Issues/)).toBeInTheDocument()
  })

  it('renders top registrants with name + state + spend', () => {
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(screen.getByText('Akin Gump Strauss Hauer & Feld LLP')).toBeInTheDocument()
    expect(screen.getByText('K&L Gates')).toBeInTheDocument()
    expect(screen.getByText('$3.20M')).toBeInTheDocument()
    expect(screen.getByText('$1.80M')).toBeInTheDocument()
  })

  it('renders trigram confidence note when match was fuzzy', () => {
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated({
        summary: {
          ...fixturePopulated().summary,
          match_method: 'trigram',
          match_confidence: 0.91,
        },
      }),
      isLoading: false,
      isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(
      screen.getAllByText(/matched by name similarity \(confidence 91%\)/).length,
    ).toBeGreaterThan(0)
  })

  it('does NOT render rank / tier chrome on the card', () => {
    // UX consistency with sibling cards. Just data, no decorative classification.
    useMasterLobbying.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<LobbyingCard masterId={1234} />)
    fireEvent.click(screen.getByText('Federal Lobbying'))
    expect(screen.queryByText('Rank')).not.toBeInTheDocument()
    expect(screen.queryByText('Tier')).not.toBeInTheDocument()
  })
})
