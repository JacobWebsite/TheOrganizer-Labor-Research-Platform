/**
 * CompetitorsCard tests (24Q-15).
 *
 * Covers:
 * - Loading state
 * - Error state
 * - No-NAICS empty state
 * - NAICS present but zero peers (rare-NAICS edge case)
 * - Populated state with peer table + profile links
 * - Tier badge rendering for gold/silver/bronze/stub
 * - NAICS-4 fallback summary text
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CompetitorsCard } from '@/features/employer-profile/CompetitorsCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterCompetitors: vi.fn(),
}))

import { useMasterCompetitors } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    master_id: 4036186,
    naics: '325412',
    naics_label: 'Pharmaceutical Preparation Manufacturing',
    size_band: '1K-10K',
    peers: [
      {
        master_id: 7087569,
        name: 'PFIZER, INC.',
        consolidated_workers: 5000,
        revenue_total: null,
        tier: 'gold',
        naics: '325412',
        match_basis: 'naics6',
      },
      {
        master_id: 7572656,
        name: 'EDWARDS LIFESCIENCES LLC',
        consolidated_workers: 4800,
        revenue_total: null,
        tier: 'bronze',
        naics: '325412',
        match_basis: 'naics6',
      },
      {
        master_id: 8690382,
        name: 'BAXALTA WORLDWIDE LLC',
        consolidated_workers: 5005,
        revenue_total: null,
        tier: 'stub',
        naics: '325412',
        match_basis: 'naics6',
      },
    ],
    as_of: '2026-05-08',
    ...overrides,
  }
}

describe('CompetitorsCard', () => {
  it('renders loading state', () => {
    useMasterCompetitors.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    // CollapsibleCard renders the title. Click to expand summary content.
    expect(screen.getByText('Industry Peers')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(screen.getByText(/Loading nearest peers/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterCompetitors.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(screen.getByText(/Could not load industry peers/)).toBeInTheDocument()
  })

  it('renders no-NAICS empty state', () => {
    useMasterCompetitors.mockReturnValue({
      data: {
        master_id: 4036186,
        naics: null,
        naics_label: null,
        size_band: 'unknown',
        peers: [],
        as_of: '2026-05-08',
      },
      isLoading: false,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(
      screen.getByText(/No industry classification \(NAICS\) is available/),
    ).toBeInTheDocument()
  })

  it('renders zero-peers empty state when NAICS present but no peers', () => {
    useMasterCompetitors.mockReturnValue({
      data: {
        master_id: 4036186,
        naics: '999999',
        naics_label: 'Hypothetical Rare NAICS',
        size_band: '100-1K',
        peers: [],
        as_of: '2026-05-08',
      },
      isLoading: false,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(screen.getByText(/no other employers in the same NAICS/)).toBeInTheDocument()
    // The user-facing label rendered inside the message body
    expect(screen.getByText(/Hypothetical Rare NAICS/)).toBeInTheDocument()
  })

  it('renders populated peer table with names, workers, and profile links', () => {
    useMasterCompetitors.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    // Names
    expect(screen.getByText('PFIZER, INC.')).toBeInTheDocument()
    expect(screen.getByText('EDWARDS LIFESCIENCES LLC')).toBeInTheDocument()
    expect(screen.getByText('BAXALTA WORLDWIDE LLC')).toBeInTheDocument()
    // Workforce numbers (with locale formatting)
    expect(screen.getByText('5,000')).toBeInTheDocument()
    expect(screen.getByText('4,800')).toBeInTheDocument()
    expect(screen.getByText('5,005')).toBeInTheDocument()
    // Profile links use MASTER- prefix
    const pfizerLink = screen.getByText('PFIZER, INC.').closest('a')
    expect(pfizerLink).toHaveAttribute('href', '/employers/MASTER-7087569')
    // Caveat copy mentions NAICS-6 exact when match_basis is naics6
    expect(screen.getByText(/NAICS-6 exact/)).toBeInTheDocument()
  })

  it('renders tier badges for gold/silver/bronze/stub', () => {
    useMasterCompetitors.mockReturnValue({
      data: fixturePopulated({
        peers: [
          { master_id: 1, name: 'A', consolidated_workers: 100, tier: 'gold', naics: '325412', match_basis: 'naics6' },
          { master_id: 2, name: 'B', consolidated_workers: 100, tier: 'silver', naics: '325412', match_basis: 'naics6' },
          { master_id: 3, name: 'C', consolidated_workers: 100, tier: 'bronze', naics: '325412', match_basis: 'naics6' },
          { master_id: 4, name: 'D', consolidated_workers: 100, tier: 'stub', naics: '325412', match_basis: 'naics6' },
        ],
      }),
      isLoading: false,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(screen.getByText('Gold')).toBeInTheDocument()
    expect(screen.getByText('Silver')).toBeInTheDocument()
    expect(screen.getByText('Bronze')).toBeInTheDocument()
    expect(screen.getByText('Stub')).toBeInTheDocument()
  })

  it('renders NAICS-4 fallback caveat copy', () => {
    useMasterCompetitors.mockReturnValue({
      data: fixturePopulated({
        naics: '3254',
        naics_label: 'Pharmaceutical and Medicine Manufacturing',
        peers: [
          {
            master_id: 7087569,
            name: 'PFIZER, INC.',
            consolidated_workers: 5000,
            revenue_total: null,
            tier: 'gold',
            naics: '325412',
            match_basis: 'naics4',
          },
        ],
      }),
      isLoading: false,
      isError: false,
    })
    render(<CompetitorsCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Industry Peers'))
    expect(screen.getByText(/NAICS-4 prefix/)).toBeInTheDocument()
  })
})
