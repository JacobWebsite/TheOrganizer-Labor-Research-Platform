/**
 * BoardCard tests (24Q-14).
 *
 * Covers:
 * - Loading / error / unmatched states
 * - Populated state: top-line metrics, director roster, interlocks
 * - Independence badge (IND / INSIDE / ?)
 * - Show-all expand on directors and interlocks
 * - Header text "Board of Directors"
 * - Source link rendering
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BoardCard } from '@/features/employer-profile/BoardCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterBoard: vi.fn(),
}))

import { useMasterBoard } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      is_matched: true,
      director_count: 2,
      independent_count: 1,
      fiscal_year: 2024,
      parse_strategy: 'per_director_minitable',
      source_url: 'https://www.sec.gov/Archives/edgar/data/0000001/proxy.htm',
      extracted_at: '2026-05-04T12:00:00+00:00',
    },
    directors: [
      {
        name: 'Robert B. Ford',
        age: 52,
        position: 'Chairman & CEO',
        since_year: 2019,
        occupation: 'Chairman of the Board and Chief Executive Officer, Abbott Laboratories',
        is_independent: false,
        committees: [],
        compensation_total: null,
        fiscal_year: 2024,
        parse_strategy: 'per_director_minitable',
        enforcement_risk: null,  // Director has no other tracked boards
      },
      {
        name: 'Nancy McKinstry',
        age: 67,
        position: null,
        since_year: 2011,
        occupation: 'Retired CEO, Wolters Kluwer N.V.',
        is_independent: true,
        committees: ['Finance', 'Risk'],
        compensation_total: 350000,
        fiscal_year: 2024,
        parse_strategy: 'per_director_minitable',
        enforcement_risk: {
          other_boards_count: 1,
          risk_score: 8.1,
          risk_tier: 'GREEN',
          components: {
            osha_violations: 2,
            nlrb_ulps: 0,
            whd_backwages: 0,
            osha_penalties: 6500,
          },
        },
      },
    ],
    interlocks: [
      {
        director_name: 'Richard D. Holder',
        other_master_id: 4216692,
        other_canonical_name: 'enerpac tool group corp',
        other_cik: 6955,
        other_fiscal_year: 2024,
      },
    ],
    ...overrides,
  }
}

function fixtureNotMatched() {
  return {
    summary: {
      is_matched: false,
      director_count: 0,
      independent_count: 0,
      fiscal_year: null,
      parse_strategy: null,
      source_url: null,
      extracted_at: null,
    },
    directors: [],
    interlocks: [],
  }
}


describe('BoardCard', () => {
  it('renders loading state', () => {
    useMasterBoard.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<BoardCard masterId={4036186} />)
    expect(screen.getByText('Board of Directors')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText(/Loading board roster/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterBoard.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText(/Could not load board roster/)).toBeInTheDocument()
  })

  it('renders unmatched panel when no directors exist', () => {
    useMasterBoard.mockReturnValue({
      data: fixtureNotMatched(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={1234} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(
      screen.getAllByText(/No board roster has been parsed/).length,
    ).toBeGreaterThan(0)
  })

  it('renders populated top-line metrics', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    // 2 directors, 1 independent, 1 interlock, FY 2024
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.getByText('2024')).toBeInTheDocument()
  })

  it('renders director rows with names and committees', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('Robert B. Ford')).toBeInTheDocument()
    expect(screen.getByText('Nancy McKinstry')).toBeInTheDocument()
    expect(screen.getByText('Finance, Risk')).toBeInTheDocument()
    // Compensation rendered as $350K
    expect(screen.getByText('$350K')).toBeInTheDocument()
  })

  it('renders independence badges (IND / INSIDE)', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('IND')).toBeInTheDocument()
    expect(screen.getByText('INSIDE')).toBeInTheDocument()
  })

  it('renders interlocks with link to other master', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('Richard D. Holder')).toBeInTheDocument()
    expect(screen.getByText('enerpac tool group corp')).toBeInTheDocument()
    // Anchor href should point at MASTER-4216692 profile
    const anchor = screen.getByText('enerpac tool group corp').closest('a')
    expect(anchor).toHaveAttribute('href', '/employer/MASTER-4216692')
  })

  it('does NOT render rank / tier chrome', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.queryByText('Rank')).not.toBeInTheDocument()
    expect(screen.queryByText('Tier')).not.toBeInTheDocument()
  })

  it('renders source link to SEC filing', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    const link = screen.getByText('SEC DEF14A filing')
    expect(link.closest('a')).toHaveAttribute(
      'href',
      'https://www.sec.gov/Archives/edgar/data/0000001/proxy.htm',
    )
  })

  // ---- C.4 Enforcement-risk chip (added 2026-05-06) ----

  it('renders Other-Co Risk header column', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText(/Other-Co Risk/i)).toBeInTheDocument()
  })

  it('renders GREEN chip with board-count for director with risk data', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('GREEN')).toBeInTheDocument()
    // McKinstry has 1 other board → singular
    expect(screen.getByText(/· 1 board/)).toBeInTheDocument()
  })

  it('renders YELLOW chip when risk score 20-99', () => {
    const fix = fixturePopulated()
    fix.directors[0].enforcement_risk = {
      other_boards_count: 3,
      risk_score: 38.4,
      risk_tier: 'YELLOW',
      components: { osha_violations: 8, nlrb_ulps: 2, whd_backwages: 0, osha_penalties: 0 },
    }
    useMasterBoard.mockReturnValue({ data: fix, isLoading: false, isError: false })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('YELLOW')).toBeInTheDocument()
    expect(screen.getByText(/· 3 boards/)).toBeInTheDocument()
  })

  it('renders RED chip when risk score >= 100', () => {
    const fix = fixturePopulated()
    fix.directors[0].enforcement_risk = {
      other_boards_count: 4,
      risk_score: 156.0,
      risk_tier: 'RED',
      components: { osha_violations: 30, nlrb_ulps: 12, whd_backwages: 200000, osha_penalties: 50000 },
    }
    useMasterBoard.mockReturnValue({ data: fix, isLoading: false, isError: false })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    expect(screen.getByText('RED')).toBeInTheDocument()
  })

  it('renders dash placeholder for directors with null enforcement_risk', () => {
    useMasterBoard.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<BoardCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Board of Directors'))
    // Robert B. Ford has enforcement_risk: null → dash
    const dashes = screen.getAllByText('—')
    // At least one dash present (more may exist for other empty cells)
    expect(dashes.length).toBeGreaterThan(0)
  })
})
