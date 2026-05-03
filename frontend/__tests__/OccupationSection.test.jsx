import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { OccupationSection } from '@/features/employer-profile/OccupationSection'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const mockData = {
  employer_naics: '6216',
  employer_state: 'TX',
  qcew_benchmark: {
    source: 'QCEW (BLS)',
    year: 2023,
    county_fips: '48201',
    industry_code: '6216',
    local_employment: 45000,
    local_establishments: 1200,
    avg_annual_pay: 52000,
    avg_weekly_wage: 1000,
  },
  top_occupations: [
    {
      occupation_code: '29-1141',
      occupation_title: 'Registered Nurses',
      employment_2024: 3200000,
      employment_change_pct: 6.0,
      top_skills: [
        { name: 'Active Listening', importance: 4.12 },
        { name: 'Critical Thinking', importance: 3.94 },
        { name: 'Social Perceptiveness', importance: 3.82 },
      ],
      top_knowledge: [
        { name: 'Medicine and Dentistry', importance: 4.15 },
        { name: 'Psychology', importance: 3.43 },
      ],
      top_work_context: [
        { name: 'Contact With Others', value: 4.67 },
        { name: 'Face-to-Face Discussions', value: 4.33 },
      ],
      job_zone: 4,
      wages: {
        median_annual: 86070,
        pct10_annual: 63720,
        pct25_annual: 72550,
        pct75_annual: 101130,
        pct90_annual: 132680,
        median_hourly: 41.38,
      },
    },
    {
      occupation_code: '31-1120',
      occupation_title: 'Home Health Aides',
      employment_2024: 900000,
      employment_change_pct: 21.4,
      top_skills: [],
      top_knowledge: [],
      top_work_context: [],
      job_zone: 2,
      wages: null,
    },
    {
      occupation_code: '43-6013',
      occupation_title: 'Medical Secretaries',
      employment_2024: 600000,
      employment_change_pct: -2.1,
      top_skills: [],
      top_knowledge: [],
      top_work_context: [],
      job_zone: null,
      wages: { median_annual: 40350, pct10_annual: 28680, pct25_annual: 33050, pct75_annual: 48230, pct90_annual: 55960, median_hourly: 19.40 },
    },
    {
      occupation_code: '11-9111',
      occupation_title: 'Medical Managers',
      employment_2024: 480000,
      employment_change_pct: 0,
      top_skills: [],
      top_knowledge: [],
      top_work_context: [],
      job_zone: null,
      wages: null,
    },
  ],
  similar_industries: [
    { similar_industry: '6211', overlap_score: 0.85, shared_occupations: 42 },
    { similar_industry: '6214', overlap_score: 0.72, shared_occupations: 31 },
  ],
}

describe('OccupationSection', () => {
  it('renders empty state when no NAICS', () => {
    renderWithProviders(<OccupationSection data={null} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('No NAICS code available for this employer')).toBeInTheDocument()
  })

  it('renders empty state when employer_naics is null', () => {
    const data = { employer_naics: null, top_occupations: [], similar_industries: [] }
    renderWithProviders(<OccupationSection data={data} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('No NAICS code available for this employer')).toBeInTheDocument()
  })

  it('renders loading state', () => {
    renderWithProviders(<OccupationSection data={null} isLoading={true} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('Loading occupation data...')).toBeInTheDocument()
  })

  it('renders occupation table with SOC codes', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('29-1141')).toBeInTheDocument()
    expect(screen.getByText('Registered Nurses')).toBeInTheDocument()
    expect(screen.getByText('31-1120')).toBeInTheDocument()
    expect(screen.getByText('Home Health Aides')).toBeInTheDocument()
  })

  it('renders growth % with correct coloring', () => {
    const { container } = renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    // Positive growth - green
    expect(container.innerHTML).toContain('text-[#2d6a4f]')
    // Negative growth - red
    expect(container.innerHTML).toContain('text-[#c23a22]')
  })

  it('renders similar industries section when expanded', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Similar Industries (2)'))
    expect(screen.getByText('6211')).toBeInTheDocument()
    expect(screen.getByText('85.0%')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('hides similar industries by default', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('Similar Industries (2)')).toBeInTheDocument()
    expect(screen.queryByText('6211')).not.toBeInTheDocument()
  })

  // O*NET enrichment tests
  it('shows O*NET skills when occupation row is expanded', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    // Click on the Registered Nurses row (which has O*NET data)
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText('Active Listening')).toBeInTheDocument()
    expect(screen.getByText('Critical Thinking')).toBeInTheDocument()
    expect(screen.getByText('Top Skills')).toBeInTheDocument()
  })

  it('shows O*NET knowledge when expanded', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText('Medicine and Dentistry')).toBeInTheDocument()
    expect(screen.getByText('Top Knowledge')).toBeInTheDocument()
  })

  it('shows job zone badge when expanded', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText(/Zone 4/)).toBeInTheDocument()
    expect(screen.getByText(/Considerable Preparation/)).toBeInTheDocument()
  })

  it('shows work context when expanded', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText('Contact With Others')).toBeInTheDocument()
    expect(screen.getByText('Work Context')).toBeInTheDocument()
  })

  it('collapses O*NET detail on second click', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText('Active Listening')).toBeInTheDocument()
    // Click again to collapse
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.queryByText('Active Listening')).not.toBeInTheDocument()
  })

  // Wage data tests
  it('renders QCEW benchmark banner', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('Local industry benchmark:')).toBeInTheDocument()
    expect(screen.getByText(/\$52,000\/yr/)).toBeInTheDocument()
    expect(screen.getByText(/\$1,000\/wk/)).toBeInTheDocument()
    expect(screen.getByText(/2023 QCEW/)).toBeInTheDocument()
  })

  it('hides QCEW banner when no benchmark data', () => {
    const dataWithoutQcew = { ...mockData, qcew_benchmark: null }
    renderWithProviders(<OccupationSection data={dataWithoutQcew} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.queryByText('Local industry benchmark:')).not.toBeInTheDocument()
  })

  it('renders Median Wage column header', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('Median Wage')).toBeInTheDocument()
  })

  it('shows formatted wage in table cell', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    expect(screen.getByText('$86,070')).toBeInTheDocument()
  })

  it('shows -- for occupations with null wages', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    // Home Health Aides and Medical Managers have null wages - there should be -- indicators
    const dashes = screen.getAllByText('--')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('shows wage percentiles in expanded detail row', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    fireEvent.click(screen.getByText('Registered Nurses'))
    expect(screen.getByText('Wage Range (TX)')).toBeInTheDocument()
    expect(screen.getByText('10th pct')).toBeInTheDocument()
    expect(screen.getByText('90th pct')).toBeInTheDocument()
    expect(screen.getByText('$63,720')).toBeInTheDocument()
    expect(screen.getByText('$132,680')).toBeInTheDocument()
    expect(screen.getByText('$41.38/hr')).toBeInTheDocument()
  })

  it('makes rows with only wages expandable', () => {
    renderWithProviders(<OccupationSection data={mockData} isLoading={false} />)
    fireEvent.click(screen.getByText('Workforce Occupations'))
    // Medical Secretaries has no O*NET but has wages - should be expandable
    fireEvent.click(screen.getByText('Medical Secretaries'))
    // $40,350 appears in both table cell and expanded detail
    expect(screen.getAllByText('$40,350').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('$19.40/hr')).toBeInTheDocument()
  })
})
