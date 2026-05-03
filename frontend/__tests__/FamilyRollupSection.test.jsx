/**
 * FamilyRollupSection tests.
 *
 * Covers: loading / error / empty states, self-gating behavior
 * (hides when master_count < 5 AND NLRB cases < 20), tile rendering,
 * expand-collapse of respondent-variants table + recent-elections table,
 * docket-URL link rendering, and the F-7 prop path.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FamilyRollupSection } from '@/features/employer-profile/FamilyRollupSection'

// Mock both hooks so tests can inject fixture data.
vi.mock('@/shared/api/profile', () => ({
  useEmployerFamilyRollup: vi.fn(),
  useEmployerFamilyRollupForF7: vi.fn(),
}))

import {
  useEmployerFamilyRollup,
  useEmployerFamilyRollupForF7,
} from '@/shared/api/profile'

function fixtureRollup(overrides = {}) {
  return {
    master_id: 4598237,
    display_name: 'STARBUCKS CORP',
    family_stem: 'starbucks',
    match_pattern: '%starbucks%',
    master_count: 380,
    masters_by_source: [
      { source_origin: 'f7', n: 235, total_reported_emp: 5637, with_emp: 232 },
      { source_origin: 'osha', n: 89, total_reported_emp: 10698, with_emp: 86 },
    ],
    nlrb: {
      totals: {
        total: 2351, rc: 888, ca: 1217, cb: 138, rm: 70, rd: 37,
        earliest: '2023-12-06', latest: '2026-01-21',
      },
      elections_summary: {
        total_elections: 791, union_won: 669, union_lost: 120,
        total_votes: 12620, total_eligible: 17814, win_rate_pct: 84.6,
      },
      elections_by_year: [
        { year: 2022, total: 346, won: 285, lost: 60 },
        { year: 2023, total: 128, won: 107, lost: 21 },
      ],
      elections_by_state: [
        { state: 'WA', elections: 86, won: 71, lost: 15 },
        { state: 'CA', elections: 74, won: 54, lost: 19 },
      ],
      recent_elections: [
        {
          case_number: '15-RC-375242',
          election_date: '2026-01-06',
          union_won: true,
          total_votes: 25,
          eligible_voters: 30,
          vote_margin: 10,
          case_docket_url: 'https://www.nlrb.gov/case/15-RC-375242',
          respondent_names: 'Starbucks Corporation',
        },
      ],
      allegations_by_section: [
        { section: '8(a)(1)', n: 1402, distinct_cases: 769 },
        { section: '8(a)(3)', n: 1120, distinct_cases: 793 },
      ],
      respondent_variants: [
        { participant_name: 'Starbucks Corporation', cases: 2099 },
        { participant_name: 'STARBUCKS CORPORATION', cases: 153 },
      ],
    },
    osha: { totals: { establishments: 139, states_covered: 31, total_inspections: 143 } },
    whd: { totals: { cases: 35, distinct_legal_names: 12 } },
    f7: { locals_count: 234, states_covered: 44 },
    ...overrides,
  }
}

describe('FamilyRollupSection', () => {
  it('returns null when neither masterId nor f7Id is provided', () => {
    useEmployerFamilyRollup.mockReturnValue({ data: null, isLoading: false, isError: false })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    const { container } = render(<FamilyRollupSection />)
    expect(container.innerHTML).toBe('')
  })

  it('renders loading state (CollapsibleCard header visible)', () => {
    useEmployerFamilyRollup.mockReturnValue({ data: null, isLoading: true, isError: false })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    render(<FamilyRollupSection masterId={4598237} />)
    // Header "Corporate Family Rollup" is always visible; expand to see body
    expect(screen.getByText('Corporate Family Rollup')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Corporate Family Rollup'))
    expect(screen.getByText(/Loading family-rollup data/)).toBeInTheDocument()
  })

  it('renders error state when query errors', () => {
    useEmployerFamilyRollup.mockReturnValue({
      data: null, isLoading: false, isError: true, error: new Error('boom'),
    })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    render(<FamilyRollupSection masterId={4598237} />)
    fireEvent.click(screen.getByText('Corporate Family Rollup'))
    expect(screen.getByText(/Failed to load family rollup/)).toBeInTheDocument()
  })

  it('self-gates and renders null when master_count < 5 AND NLRB < 20', () => {
    useEmployerFamilyRollup.mockReturnValue({
      data: fixtureRollup({
        master_count: 2,
        nlrb: { ...fixtureRollup().nlrb, totals: { ...fixtureRollup().nlrb.totals, total: 10 } },
      }),
      isLoading: false,
      isError: false,
    })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    const { container } = render(<FamilyRollupSection masterId={4598237} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders when master_count exceeds threshold', () => {
    useEmployerFamilyRollup.mockReturnValue({
      data: fixtureRollup(), isLoading: false, isError: false,
    })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    render(<FamilyRollupSection masterId={4598237} />)
    // defaultOpen=true for the populated path, so content is in DOM. Banner
    // should include the master count; use getAllByText because the literal
    // '380 variant records' may appear both in the banner and aria-label/title.
    const matches = screen.getAllByText((_, el) => el?.textContent?.includes('380 variant records'))
    expect(matches.length).toBeGreaterThan(0)
    // Win rate should show in the tile sublabel
    const winRateMatches = screen.getAllByText((_, el) => el?.textContent?.includes('84.6% win rate'))
    expect(winRateMatches.length).toBeGreaterThan(0)
  })

  it('renders the case docket URL as a hyperlink', () => {
    useEmployerFamilyRollup.mockReturnValue({
      data: fixtureRollup(), isLoading: false, isError: false,
    })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    render(<FamilyRollupSection masterId={4598237} />)
    const link = screen.getByRole('link', { name: '15-RC-375242' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://www.nlrb.gov/case/15-RC-375242')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('expands and collapses the respondent-variants table', () => {
    const many = Array.from({ length: 15 }, (_, i) => ({
      participant_name: `Variant ${i + 1}`,
      cases: 100 - i,
    }))
    useEmployerFamilyRollup.mockReturnValue({
      data: fixtureRollup({
        nlrb: { ...fixtureRollup().nlrb, respondent_variants: many },
      }),
      isLoading: false,
      isError: false,
    })
    useEmployerFamilyRollupForF7.mockReturnValue({ data: null, isLoading: false, isError: false })
    render(<FamilyRollupSection masterId={4598237} />)
    // Default view shows 8 variants
    expect(screen.getByText('Variant 1')).toBeInTheDocument()
    expect(screen.getByText('Variant 8')).toBeInTheDocument()
    expect(screen.queryByText('Variant 9')).not.toBeInTheDocument()
    // Click "Show all 15" toggle
    fireEvent.click(screen.getByText(/Show all 15/))
    expect(screen.getByText('Variant 9')).toBeInTheDocument()
    expect(screen.getByText('Variant 15')).toBeInTheDocument()
  })

  it('uses the F-7 hook when only f7Id is passed', () => {
    useEmployerFamilyRollup.mockReturnValue({ data: null, isLoading: false, isError: false })
    useEmployerFamilyRollupForF7.mockReturnValue({
      data: fixtureRollup({ resolved_from_f7: '6de45fd2d423c993' }),
      isLoading: false,
      isError: false,
    })
    render(<FamilyRollupSection f7Id="6de45fd2d423c993" />)
    expect(useEmployerFamilyRollupForF7).toHaveBeenCalledWith(
      '6de45fd2d423c993',
      expect.any(Object),
    )
    // Still renders the 380-variant banner
    const matches = screen.getAllByText((_, el) => el?.textContent?.includes('380 variant records'))
    expect(matches.length).toBeGreaterThan(0)
  })
})
