import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { WorkforceDemographicsCard } from '@/features/employer-profile/WorkforceDemographicsCard'

// Mock the apiClient
vi.mock('@/shared/api/client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

import { apiClient } from '@/shared/api/client'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const mockWorkforceProfile = {
  employer_id: 'test-123',
  employer_name: 'Acme Corp',
  state: 'CA',
  city: 'Los Angeles',
  naics: '6216',
  unit_size: 50,
  estimated_composition: {
    method: 'blended',
    weights: { acs: 0.6, lodes: 0.4 },
    note: 'ACS (industry x state) weighted 60%, LODES (county geography) weighted 40%',
    gender: [
      { label: 'Female', pct: 72.5 },
      { label: 'Male', pct: 27.5 },
    ],
    race: [
      { label: 'White', pct: 45.0 },
      { label: 'Black/African American', pct: 25.0 },
      { label: 'Asian/Pacific Islander', pct: 18.0 },
      { label: 'Other', pct: 12.0 },
    ],
    hispanic: [
      { label: 'Not Hispanic/Latino', pct: 72.0 },
      { label: 'Hispanic/Latino', pct: 28.0 },
    ],
    age: [
      { label: '30-54', pct: 55.0 },
      { label: '55+', pct: 28.0 },
      { label: '29 or younger', pct: 17.0 },
    ],
    education: [
      { label: "Some college/Associate's", pct: 30.0 },
      { label: "Bachelor's+", pct: 25.0 },
      { label: 'HS diploma/GED', pct: 22.0 },
      { label: 'No HS diploma', pct: 23.0 },
    ],
  },
  acs: {
    source: 'ACS (Census Bureau)',
    level: 'industry',
    naics_matched: '6216',
    total_workers: 250000,
    gender: [
      { label: 'Female', pct: 75.2 },
      { label: 'Male', pct: 24.8 },
    ],
    race: [{ label: 'White', pct: 45.0 }],
    hispanic: [{ label: 'Not Hispanic/Latino', pct: 72.0 }, { label: 'Hispanic/Latino', pct: 28.0 }],
    age: [{ label: 'Under 25', pct: 12.0 }],
    education: [{ label: 'HS diploma/GED', pct: 22.0 }],
  },
  lodes: {
    source: 'LODES 2022 (Census Bureau)',
    county_fips: '06037',
    total_jobs: 2404751,
    demo_total_jobs: 897513,
    gender: [{ label: 'Male', pct: 50.0 }, { label: 'Female', pct: 50.0 }],
    race: [{ label: 'White', pct: 55.0 }],
    hispanic: [{ label: 'Hispanic/Latino', pct: 25.0 }],
    age: [{ label: '30-54', pct: 52.0 }],
    education: [{ label: "Bachelor's+", pct: 30.0 }],
  },
  qcew: {
    source: 'QCEW (BLS)',
    year: 2023,
    local_employment: 15000,
    local_establishments: 200,
    avg_annual_pay: 45000,
  },
  soii: {
    source: 'SOII (BLS)',
    year: 2024,
    industry: 'Home Health Care Services',
    total_recordable_rate: 4.5,
    per: '100 full-time workers',
  },
  jolts: {
    source: 'JOLTS (BLS)',
    year: 2025,
    rates: { 'Hires': 3.5, 'Quits': 2.1, 'Total separations': 2.8 },
  },
  ncs: null,
  oes: null,
  union_density: {
    state: { year: 2024, union_density_pct: 15.5, represented_pct: 16.2, total_employed_k: 18000 },
  },
  tract: {
    source: 'ACS Tract (Census Bureau)',
    tract_fips: '06037264100',
    total_population: 4500,
    median_household_income: 52000,
    unemployment_rate: 6.2,
    pct_female: 51.3,
    pct_minority: 68.5,
    gender: [
      { label: 'Male', pct: 48.7 },
      { label: 'Female', pct: 51.3 },
    ],
    race: [
      { label: 'White', pct: 31.5 },
      { label: 'Black/African American', pct: 22.0 },
      { label: 'Asian', pct: 18.5 },
    ],
    hispanic: [
      { label: 'Not Hispanic/Latino', pct: 62.0 },
      { label: 'Hispanic/Latino', pct: 38.0 },
    ],
    education: [
      { label: 'No HS diploma', pct: 20.0 },
      { label: 'HS diploma/GED', pct: 25.0 },
      { label: "Some college/Associate's", pct: 25.0 },
      { label: "Bachelor's", pct: 18.0 },
      { label: 'Graduate+', pct: 12.0 },
    ],
  },
}

describe('WorkforceDemographicsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when employerId is missing', () => {
    const { container } = renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders loading state', () => {
    apiClient.get.mockReturnValue(new Promise(() => {})) // never resolves
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(screen.getByText('Loading workforce profile...')).toBeInTheDocument()
  })

  it('renders estimated composition when data loads', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('Estimated Workforce Composition')).toBeInTheDocument()
    // Multiple sections may exist (estimate + source breakdowns), so use getAllByText
    expect(screen.getAllByText('Gender').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Race/Ethnicity').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Hispanic/Latino Origin').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Age Distribution')).toBeInTheDocument()
    expect(screen.getAllByText('Education').length).toBeGreaterThanOrEqual(1)
  })

  it('renders blended gender percentages', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    const females = await screen.findAllByText('Female')
    expect(females.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('72.5%')).toBeInTheDocument()
    expect(screen.getByText('27.5%')).toBeInTheDocument()
  })

  it('renders data source badges', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Estimated Workforce Composition')
    expect(screen.getByText('ACS')).toBeInTheDocument()
    expect(screen.getByText('LODES')).toBeInTheDocument()
    expect(screen.getByText('QCEW')).toBeInTheDocument()
    expect(screen.getByText('JOLTS')).toBeInTheDocument()
  })

  it('renders industry context section with QCEW and SOII', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Industry & Local Context')
    expect(screen.getByText('15,000')).toBeInTheDocument() // local employment
    expect(screen.getByText('$45,000')).toBeInTheDocument() // avg pay
    expect(screen.getByText('4.5')).toBeInTheDocument() // injury rate
  })

  it('renders union density from CPS', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Industry & Local Context')
    expect(screen.getByText('15.5%')).toBeInTheDocument() // state union density
  })

  it('renders JOLTS turnover rates', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText(/Turnover Rates/)
    expect(screen.getByText('Hires:')).toBeInTheDocument()
    expect(screen.getByText(/3.5%/)).toBeInTheDocument()
  })

  it('renders blending method note', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText(/Blended from ACS/)).toBeInTheDocument()
    expect(screen.getByText(/60%/)).toBeInTheDocument()
  })

  it('calls workforce-profile API with employer ID', () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    expect(apiClient.get).toHaveBeenCalledWith('/api/profile/employers/test-123/workforce-profile')
  })

  it('renders acs_only method note when no LODES', async () => {
    const acsOnly = {
      ...mockWorkforceProfile,
      lodes: null,
      estimated_composition: {
        method: 'acs_only',
        demographics: mockWorkforceProfile.acs,
      },
    }
    apiClient.get.mockResolvedValue(acsOnly)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText(/Based on ACS industry baseline/)).toBeInTheDocument()
  })

  it('renders neighborhood demographics when tract present', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('Neighborhood Demographics')).toBeInTheDocument()
    expect(screen.getByText(/06037264100/)).toBeInTheDocument()
    expect(screen.getByText('$52,000')).toBeInTheDocument()
    expect(screen.getByText('6.2%')).toBeInTheDocument()
    expect(screen.getByText('4,500')).toBeInTheDocument()
  })

  it('does not render neighborhood section when tract is null', async () => {
    const noTract = { ...mockWorkforceProfile, tract: null }
    apiClient.get.mockResolvedValue(noTract)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Estimated Workforce Composition')
    expect(screen.queryByText('Neighborhood Demographics')).not.toBeInTheDocument()
  })

  it('renders Tract/ACS source badge when tract present', async () => {
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Estimated Workforce Composition')
    expect(screen.getByText('Tract/ACS')).toBeInTheDocument()
  })

  it('renders nothing when API returns error', async () => {
    apiClient.get.mockRejectedValue(new Error('Not found'))
    const { container } = renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    // Wait for error state to settle
    await new Promise(r => setTimeout(r, 100))
    // Card renders nothing on error
    expect(container.querySelector('[data-testid]')).toBeNull()
  })

  // --- gate_v1 method tests ---

  it('renders gate_v1 method with description', async () => {
    const gateV1Profile = {
      ...mockWorkforceProfile,
      estimated_composition: {
        method: 'gate_v1',
        race: [
          { label: 'White', pct: 62.5, range_low: 55.0, range_high: 70.0 },
          { label: 'Black', pct: 15.2, range_low: 8.0, range_high: 22.0 },
          { label: 'Asian', pct: 12.0, range_low: 8.5, range_high: 16.0 },
          { label: 'AIAN', pct: 0.5 },
          { label: 'NHOPI', pct: 0.3 },
          { label: 'Two+', pct: 1.5 },
        ],
        hispanic: [
          { label: 'Hispanic', pct: 18.0, range_low: 12.0, range_high: 25.0 },
          { label: 'Not Hispanic', pct: 82.0, range_low: 75.0, range_high: 88.0 },
        ],
        gender: [
          { label: 'Female', pct: 45.0, range_low: 35.0, range_high: 55.0 },
          { label: 'Male', pct: 55.0, range_low: 45.0, range_high: 65.0 },
        ],
        confidence_tier: 'GREEN',
        range_context: {
          interval: '70%',
          lookup_cell: 'Finance/Insurance (52)|Med-Low',
          cell_n: 709,
        },
      },
    }
    apiClient.get.mockResolvedValue(gateV1Profile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('Estimated Workforce Composition')).toBeInTheDocument()
    expect(screen.getByText(/Model-based estimate/)).toBeInTheDocument()
    expect(screen.getByText(/14,000/)).toBeInTheDocument()
  })

  it('renders range text for items with ranges', async () => {
    const gateV1Profile = {
      ...mockWorkforceProfile,
      estimated_composition: {
        method: 'gate_v1',
        race: [
          { label: 'White', pct: 62.5, range_low: 55.0, range_high: 70.0 },
          { label: 'AIAN', pct: 0.5 },
        ],
        hispanic: null,
        gender: null,
      },
    }
    apiClient.get.mockResolvedValue(gateV1Profile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    // White should show range text
    expect(await screen.findByText('62.5% (55-70)')).toBeInTheDocument()
    // AIAN has no range, shows pct only
    expect(screen.getByText('0.5%')).toBeInTheDocument()
  })

  it('renders confidence badge', async () => {
    const gateV1Profile = {
      ...mockWorkforceProfile,
      estimated_composition: {
        method: 'gate_v1',
        race: [{ label: 'White', pct: 60.0 }],
        hispanic: null,
        gender: null,
        confidence_tier: 'GREEN',
        range_context: { interval: '70%', lookup_cell: 'test|cell', cell_n: 500 },
      },
    }
    apiClient.get.mockResolvedValue(gateV1Profile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('High confidence')).toBeInTheDocument()
    expect(screen.getByText(/500 similar employers/)).toBeInTheDocument()
  })

  it('renders YELLOW confidence badge', async () => {
    const gateV1Profile = {
      ...mockWorkforceProfile,
      estimated_composition: {
        method: 'gate_v1',
        race: [{ label: 'White', pct: 60.0 }],
        hispanic: null,
        gender: null,
        confidence_tier: 'YELLOW',
        range_context: { interval: '70%', lookup_cell: 'test|cell', cell_n: 200 },
      },
    }
    apiClient.get.mockResolvedValue(gateV1Profile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('Moderate confidence')).toBeInTheDocument()
  })

  it('renders range band behind bar', async () => {
    const gateV1Profile = {
      ...mockWorkforceProfile,
      estimated_composition: {
        method: 'gate_v1',
        race: [{ label: 'White', pct: 62.5, range_low: 55.0, range_high: 70.0 }],
        hispanic: null,
        gender: null,
      },
    }
    apiClient.get.mockResolvedValue(gateV1Profile)
    const { container } = renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    await screen.findByText('Estimated Workforce Composition')
    const rangeBand = container.querySelector('[data-testid="range-band"]')
    expect(rangeBand).not.toBeNull()
  })

  it('old responses without ranges still work', async () => {
    // Original blended method without any range fields
    apiClient.get.mockResolvedValue(mockWorkforceProfile)
    renderWithProviders(
      <WorkforceDemographicsCard state="CA" naics="6216" employerId="test-123" />
    )
    fireEvent.click(screen.getByText('Workforce Demographics'))
    expect(await screen.findByText('Estimated Workforce Composition')).toBeInTheDocument()
    expect(screen.getByText('72.5%')).toBeInTheDocument()
  })
})
