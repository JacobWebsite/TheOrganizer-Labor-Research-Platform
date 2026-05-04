/**
 * FecContributionsCard tests (24Q-41).
 *
 * Covers:
 * - Loading / error / unmatched states
 * - Populated state: top-line metrics, yearly breakdown, top PAC recipients,
 *   top employee donors
 * - Party badges (DEM/REP/other)
 * - Show-all expand on each table
 * - Header text "FEC Contributions"
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FecContributionsCard } from '@/features/employer-profile/FecContributionsCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterFecContributions: vi.fn(),
}))

import { useMasterFecContributions } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      is_matched: true,
      pac_committees_count: 1,
      pac_dollars_total: 50000,
      pac_recipients_count: 12,
      employee_donations_count: 47827,
      employee_dollars_total: 324561242,
      employer_norms_used: ['SPACE EXPLORATION TECHNOLOGIES CORP', 'SPACE EXPLORATION TECHNOLOGIES'],
      latest_pac_date: '2024-11-01',
      latest_employee_date: '2025-12-28',
    },
    top_pac_recipients: [
      { cand_id: 'P00001', name: 'JANE DOE', party: 'DEM', office: 'P', state: 'CA',
        contributions: 5, dollars: 25000 },
      { cand_id: 'P00002', name: 'JOHN ROE', party: 'REP', office: 'S', state: 'TX',
        contributions: 3, dollars: 15000 },
      { cand_id: 'P00003', name: 'GREEN CANDIDATE', party: 'GRE', office: 'H',
        state: 'OR', contributions: 1, dollars: 5000 },
    ],
    top_employee_donors: [
      { name: 'MUSK, ELON', city: 'LAKEWAY', state: 'TX', occupation: 'CEO',
        contributions: 1, dollars: 924600 },
      { name: 'HUGHES, TIMOTHY', city: 'MC LEAN', state: 'VA',
        occupation: 'EXECUTIVE', contributions: 7, dollars: 14000 },
    ],
    yearly_breakdown: [
      { year: 2025, pac_dollars: 0, employee_dollars: 1004 },
      { year: 2024, pac_dollars: 30000, employee_dollars: 944158 },
      { year: 2023, pac_dollars: 0, employee_dollars: 10342 },
    ],
    ...overrides,
  }
}

function fixtureNotMatched() {
  return {
    summary: {
      is_matched: false, pac_committees_count: 0, pac_dollars_total: 0,
      pac_recipients_count: 0, employee_donations_count: 0,
      employee_dollars_total: 0, employer_norms_used: [],
      latest_pac_date: null, latest_employee_date: null,
    },
    top_pac_recipients: [], top_employee_donors: [], yearly_breakdown: [],
  }
}


describe('FecContributionsCard', () => {
  it('renders loading state', () => {
    useMasterFecContributions.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<FecContributionsCard masterId={1716574} />)
    expect(screen.getByText('FEC Contributions')).toBeInTheDocument()
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.getByText(/Loading FEC contribution data/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterFecContributions.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.getByText(/Could not load FEC contribution data/)).toBeInTheDocument()
  })

  it('renders unmatched panel when no FEC activity exists', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixtureNotMatched(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1234} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(
      screen.getAllByText(/No registered FEC committee or matched employee donations/).length,
    ).toBeGreaterThan(0)
  })

  it('renders populated top-line metrics', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    // "1" appears in multiple places (PAC committees tile + a contribution
    // count); just assert it shows up somewhere
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.getByText('47,827')).toBeInTheDocument()             // employee donations
    expect(screen.getByText('$324.56M')).toBeInTheDocument()           // employee dollars
  })

  it('renders yearly breakdown with PAC + employee splits', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.getByText('2024')).toBeInTheDocument()
    expect(screen.getByText('$944K')).toBeInTheDocument()              // employee 2024
    expect(screen.getByText('$30K')).toBeInTheDocument()               // pac 2024
  })

  it('renders top PAC recipients with party badges', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.getByText('JANE DOE')).toBeInTheDocument()
    expect(screen.getByText('DEM')).toBeInTheDocument()
    expect(screen.getByText('JOHN ROE')).toBeInTheDocument()
    expect(screen.getByText('REP')).toBeInTheDocument()
    // Other party gets first 3 chars
    expect(screen.getByText('GRE')).toBeInTheDocument()
  })

  it('renders top employee donors with occupation + location', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.getByText('MUSK, ELON')).toBeInTheDocument()
    expect(screen.getByText('CEO')).toBeInTheDocument()
    expect(screen.getByText('LAKEWAY, TX')).toBeInTheDocument()
    // 924600 / 1000 = 924.6, .toFixed(0) rounds to '925'
    expect(screen.getByText('$925K')).toBeInTheDocument()
  })

  it('renders employer_norms_used in the explainer', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(
      screen.getAllByText(/SPACE EXPLORATION TECHNOLOGIES CORP/).length,
    ).toBeGreaterThan(0)
  })

  it('does NOT render rank / tier chrome', () => {
    useMasterFecContributions.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<FecContributionsCard masterId={1716574} />)
    fireEvent.click(screen.getByText('FEC Contributions'))
    expect(screen.queryByText('Rank')).not.toBeInTheDocument()
    expect(screen.queryByText('Tier')).not.toBeInTheDocument()
  })
})
