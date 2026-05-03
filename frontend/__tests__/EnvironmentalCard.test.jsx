/**
 * EnvironmentalCard tests (24Q-31).
 *
 * Covers:
 * - Loading state
 * - Error state
 * - "No records matched" empty state
 * - Populated state: summary stats + facility table
 * - SNC badge rendering for significant non-complier facilities
 * - Show-all expand/collapse for facility table
 * - Vintage date / freshness footer rendering
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EnvironmentalCard } from '@/features/employer-profile/EnvironmentalCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterEpaEcho: vi.fn(),
}))

// SourceFreshnessFooter calls useQuery internally; stub it out so this test
// doesn't need a QueryClientProvider. Pattern matches other card tests.
vi.mock('@/shared/components/SourceFreshnessFooter', () => ({
  SourceFreshnessFooter: () => null,
}))

import { useMasterEpaEcho } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      total_facilities: 8,
      active_facilities: 7,
      total_inspections: 14,
      total_formal_actions: 12,
      total_informal_actions: 3,
      total_penalties: 5300000,
      snc_facilities: 2,
    },
    facilities: [
      {
        registry_id: '110004623818',
        facility_name: 'EXAMPLE PLANT 1',
        city: 'CLEVELAND',
        state: 'OH',
        zip: '44105',
        naics: '492210',
        active: true,
        snc_flag: true,
        inspection_count: 5,
        formal_action_count: 4,
        informal_action_count: 1,
        total_penalties: 2100000,
        last_inspection_date: '2022-09-15',
        last_formal_action_date: '2022-10-01',
        last_penalty_date: '2022-10-17',
        compliance_status: 'In Violation',
        match_confidence: 0.92,
      },
      {
        registry_id: '110009609263',
        facility_name: 'EXAMPLE PLANT 2',
        city: 'PIQUA',
        state: 'OH',
        zip: '45356',
        naics: '447190',
        active: true,
        snc_flag: false,
        inspection_count: 3,
        formal_action_count: 2,
        informal_action_count: 0,
        total_penalties: 1500000,
        last_inspection_date: '2021-11-02',
        last_formal_action_date: null,
        last_penalty_date: null,
        compliance_status: 'No Violation Identified',
        match_confidence: 0.85,
      },
    ],
    latest_record_date: '2022-10-17',
    ...overrides,
  }
}

function fixtureEmpty() {
  return {
    summary: {
      total_facilities: 0,
      active_facilities: 0,
      total_inspections: 0,
      total_formal_actions: 0,
      total_informal_actions: 0,
      total_penalties: 0,
      snc_facilities: 0,
    },
    facilities: [],
    latest_record_date: null,
  }
}

describe('EnvironmentalCard', () => {
  it('renders loading state', () => {
    useMasterEpaEcho.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<EnvironmentalCard masterId={142224} />)
    expect(screen.getByText('EPA Environmental Record')).toBeInTheDocument()
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    expect(screen.getByText(/Loading EPA enforcement data/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterEpaEcho.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<EnvironmentalCard masterId={142224} />)
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    expect(screen.getByText(/Could not load EPA ECHO data/)).toBeInTheDocument()
  })

  it('renders no-records-matched panel for empty data', () => {
    useMasterEpaEcho.mockReturnValue({
      data: fixtureEmpty(),
      isLoading: false,
      isError: false,
    })
    render(<EnvironmentalCard masterId={142224} />)
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    expect(
      screen.getByText(/No EPA ECHO facilities have been matched/),
    ).toBeInTheDocument()
    // Critical UX clarification: no-data is not no-violations
    expect(screen.getByText(/does/)).toBeInTheDocument()
  })

  it('renders populated summary stats', () => {
    useMasterEpaEcho.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<EnvironmentalCard masterId={142224} />)
    // CollapsibleCard expands when populated; click header to ensure visibility
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    // Labels appear in both summary tiles and table headers; use getAllByText.
    expect(screen.getAllByText('Facilities').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Inspections').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Formal Actions').length).toBeGreaterThan(0)
    expect(screen.getByText('Total Penalties')).toBeInTheDocument()
    // Numbers visible
    expect(screen.getByText('8')).toBeInTheDocument()      // total_facilities
    expect(screen.getByText('14')).toBeInTheDocument()     // total_inspections
    expect(screen.getByText('12')).toBeInTheDocument()     // total_formal_actions
  })

  it('renders SNC badge for significant non-complier facilities', () => {
    useMasterEpaEcho.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<EnvironmentalCard masterId={142224} />)
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    expect(screen.getByText('SNC')).toBeInTheDocument()
  })

  it('renders the freshness footer with vintage date', () => {
    useMasterEpaEcho.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<EnvironmentalCard masterId={142224} />)
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    expect(screen.getByText(/EPA data current through/)).toBeInTheDocument()
  })

  it('shows expand button when more than VISIBLE_ROWS facilities exist', () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      registry_id: `R${i}`,
      facility_name: `Facility ${i + 1}`,
      city: 'CITY',
      state: 'OH',
      zip: '00000',
      naics: '484110',
      active: true,
      snc_flag: false,
      inspection_count: 1,
      formal_action_count: 0,
      informal_action_count: 0,
      total_penalties: 1000 - i,
      last_inspection_date: null,
      last_formal_action_date: null,
      last_penalty_date: null,
      compliance_status: null,
      match_confidence: 0.85,
    }))
    useMasterEpaEcho.mockReturnValue({
      data: fixturePopulated({
        summary: { ...fixturePopulated().summary, total_facilities: 12 },
        facilities: many,
      }),
      isLoading: false,
      isError: false,
    })
    render(<EnvironmentalCard masterId={142224} />)
    fireEvent.click(screen.getByText('EPA Environmental Record'))
    // Default: 5 visible
    expect(screen.getByText('Facility 1')).toBeInTheDocument()
    expect(screen.getByText('Facility 5')).toBeInTheDocument()
    expect(screen.queryByText('Facility 6')).not.toBeInTheDocument()
    // Expand
    fireEvent.click(screen.getByText(/Show all 12 facilities/))
    expect(screen.getByText('Facility 12')).toBeInTheDocument()
  })
})
