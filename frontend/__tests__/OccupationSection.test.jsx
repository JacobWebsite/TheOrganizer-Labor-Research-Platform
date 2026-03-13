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
})
