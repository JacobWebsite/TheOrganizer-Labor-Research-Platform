/**
 * FacilitiesMapCard tests (Week 3 A.2).
 *
 * Covers:
 * - Loading / error states
 * - Empty state (zero geocoded facilities)
 * - Populated header with summary text
 * - Layer-toggle chips (one per source with count > 0)
 * - Toggling a chip filters which sources reach the map
 * - Reset button restores all sources
 *
 * The lazy-loaded `FacilitiesLeafletMap` is mocked so jsdom never has
 * to instantiate real Leaflet (which depends on browser-only APIs).
 * The mock surfaces the facilities array as testable DOM so we can
 * assert filter behavior.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { FacilitiesMapCard } from '@/features/employer-profile/FacilitiesMapCard'

// Stub the inner map. Renders the visible facilities as a list of test
// hooks so we can assert which markers would be drawn for a given
// filter state. The lazy() boundary still resolves, but we never touch
// `react-leaflet` or `leaflet` itself.
vi.mock('@/features/employer-profile/FacilitiesLeafletMap.jsx', () => ({
  default: ({ facilities }) => (
    <div data-testid="leaflet-stub">
      <span data-testid="leaflet-marker-count">{facilities.length}</span>
      <ul>
        {facilities.map((f) => (
          <li key={f.id} data-testid={`leaflet-marker-${f.source}`}>
            {f.label}
          </li>
        ))}
      </ul>
    </div>
  ),
}))

vi.mock('@/shared/api/profile', () => ({
  useMasterFacilities: vi.fn(),
}))

import { useMasterFacilities } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      total_facilities: 4,
      by_source: { epa: 2, f7: 1, mergent: 1 },
      states: ['IL', 'OH'],
    },
    facilities: [
      {
        id: 'epa-110001338437',
        source: 'epa',
        lat: 42.27742,
        lng: -87.87686,
        label: 'ABBOTT LABORATORIES',
        address: '100 ABBOTT PARK RD',
        city: 'LAKE BLUFF',
        state: 'IL',
        zip: '60044',
        extra: {
          registry_id: '110001338437',
          active: true,
          snc_flag: false,
          inspection_count: 3,
          formal_action_count: 1,
          total_penalties: 50000,
        },
      },
      {
        id: 'epa-110005967338',
        source: 'epa',
        lat: 42.3159,
        lng: -87.86479,
        label: 'ABBOTT LABORATORIES',
        address: '1300 SHERIDAN RD',
        city: 'NORTH CHICAGO',
        state: 'IL',
        zip: '60064',
        extra: {
          registry_id: '110005967338',
          active: true,
          snc_flag: true,
          inspection_count: 5,
          formal_action_count: 3,
          total_penalties: 250000,
        },
      },
      {
        id: 'f7-abc123',
        source: 'f7',
        lat: 41.5,
        lng: -88.0,
        label: 'Acme Plant',
        address: '1 Plant Way',
        city: 'JOLIET',
        state: 'IL',
        zip: '60401',
        extra: {
          employer_id: 'abc123',
          latest_unit_size: 320,
          latest_union_name: 'UAW',
          latest_union_fnum: '12345',
          latest_notice_date: '2024-06-01',
        },
      },
      {
        id: 'mergent-001234567',
        source: 'mergent',
        lat: 39.96,
        lng: -82.99,
        label: 'Acme Corp HQ',
        address: '500 HQ Blvd',
        city: 'COLUMBUS',
        state: 'OH',
        zip: '43215',
        extra: {
          duns: '001234567',
          employees_site: 1500,
          employees_all_sites: 5200,
          location_type: 'Headquarters',
        },
      },
    ],
    ...overrides,
  }
}

function fixtureEmpty() {
  return {
    summary: {
      total_facilities: 0,
      by_source: { epa: 0, f7: 0, mergent: 0 },
      states: [],
    },
    facilities: [],
  }
}

describe('FacilitiesMapCard', () => {
  it('renders loading state', () => {
    useMasterFacilities.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<FacilitiesMapCard masterId={4036186} />)
    expect(screen.getByText('Facilities Map')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Facilities Map'))
    expect(screen.getByText(/Loading facility locations/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterFacilities.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<FacilitiesMapCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Facilities Map'))
    expect(screen.getByText(/Could not load facility locations/)).toBeInTheDocument()
  })

  it('renders empty-state panel when zero facilities are matched', () => {
    useMasterFacilities.mockReturnValue({
      data: fixtureEmpty(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    fireEvent.click(screen.getByText('Facilities Map'))
    expect(
      screen.getByText(/No geocoded facilities have been matched/),
    ).toBeInTheDocument()
    // UX clarification mirrors EnvironmentalCard's "no data is not no signal"
    expect(screen.getByText(/does/)).toBeInTheDocument()
  })

  it('renders populated summary header with total + state list', async () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    // Card defaults open when populated; header text is visible.
    expect(screen.getByText('4 locations')).toBeInTheDocument()
    expect(screen.getByText(/across IL, OH/)).toBeInTheDocument()
  })

  it('renders one legend chip per source with count > 0', () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    expect(screen.getByText('EPA Facilities')).toBeInTheDocument()
    expect(screen.getByText('F-7 Workplaces')).toBeInTheDocument()
    expect(screen.getByText('Mergent Sites')).toBeInTheDocument()
  })

  it('omits a legend chip when that source has zero count', () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated({
        summary: {
          total_facilities: 2,
          by_source: { epa: 2, f7: 0, mergent: 0 },
          states: ['IL'],
        },
        facilities: fixturePopulated().facilities.filter((f) => f.source === 'epa'),
      }),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    expect(screen.getByText('EPA Facilities')).toBeInTheDocument()
    expect(screen.queryByText('F-7 Workplaces')).not.toBeInTheDocument()
    expect(screen.queryByText('Mergent Sites')).not.toBeInTheDocument()
  })

  it('passes all facilities to the map by default', async () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    // Lazy boundary: wait one microtask for the dynamic import to resolve.
    const stub = await screen.findByTestId('leaflet-stub')
    expect(stub).toBeInTheDocument()
    expect(screen.getByTestId('leaflet-marker-count').textContent).toBe('4')
  })

  it('toggles a source off and updates the map marker count', async () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    await screen.findByTestId('leaflet-stub')
    expect(screen.getByTestId('leaflet-marker-count').textContent).toBe('4')

    // Click "EPA Facilities" chip to hide EPA markers (2 of 4).
    await act(async () => {
      fireEvent.click(screen.getByText('EPA Facilities'))
    })
    expect(screen.getByTestId('leaflet-marker-count').textContent).toBe('2')
  })

  it('reset filters restores all sources', async () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    await screen.findByTestId('leaflet-stub')

    await act(async () => {
      fireEvent.click(screen.getByText('EPA Facilities'))
    })
    expect(screen.getByTestId('leaflet-marker-count').textContent).toBe('2')

    await act(async () => {
      fireEvent.click(screen.getByText('Reset filters'))
    })
    expect(screen.getByTestId('leaflet-marker-count').textContent).toBe('4')
  })

  it('shows "all sources hidden" hint when every chip is off', async () => {
    useMasterFacilities.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<FacilitiesMapCard masterId={4036186} />)
    await screen.findByTestId('leaflet-stub')

    await act(async () => {
      fireEvent.click(screen.getByText('EPA Facilities'))
    })
    await act(async () => {
      fireEvent.click(screen.getByText('F-7 Workplaces'))
    })
    await act(async () => {
      fireEvent.click(screen.getByText('Mergent Sites'))
    })
    expect(screen.getByText(/All sources hidden/)).toBeInTheDocument()
  })
})
