import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { NycEnforcementSection } from '@/features/employer-profile/NycEnforcementSection'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('NycEnforcementSection', () => {
  it('renders no-records warning when nycEnforcement is null', () => {
    renderWithProviders(<NycEnforcementSection nycEnforcement={null} />)
    expect(screen.getByText('NYC Enforcement')).toBeInTheDocument()
    expect(screen.getByText('No records matched')).toBeInTheDocument()
  })

  it('renders no-records warning when record_count is 0', () => {
    const data = {
      summary: { record_count: 0, is_debarred: false, debarment_end_date: null, total_wages_owed: 0, total_recovered: 0 },
      records: [],
    }
    renderWithProviders(<NycEnforcementSection nycEnforcement={data} />)
    expect(screen.getByText('No records matched')).toBeInTheDocument()
  })

  it('renders debarment badge when is_debarred is true', () => {
    const data = {
      summary: { record_count: 2, is_debarred: true, debarment_end_date: '2027-01-01', total_wages_owed: 5000, total_recovered: 3000 },
      records: [
        { source: 'debarment', employer_name: 'Acme Corp', debarment_start_date: '2024-01-01', amount: null },
        { source: 'wage_theft_nys', employer_name: 'Acme Corp', debarment_start_date: null, amount: 5000 },
      ],
    }
    renderWithProviders(<NycEnforcementSection nycEnforcement={data} />)
    // Expand the card
    fireEvent.click(screen.getByText('NYC Enforcement'))
    expect(screen.getByText(/DEBARRED/)).toBeInTheDocument()
  })

  it('renders record count and amounts correctly', () => {
    const data = {
      summary: { record_count: 3, is_debarred: false, debarment_end_date: null, total_wages_owed: 15000, total_recovered: 8500 },
      records: [
        { source: 'local_labor_law', employer_name: 'Test LLC', debarment_start_date: '2023-06-15', amount: 8500 },
        { source: 'wage_theft_nys', employer_name: 'Test LLC', debarment_start_date: null, amount: 10000 },
        { source: 'wage_theft_nys', employer_name: 'Test LLC', debarment_start_date: null, amount: 5000 },
      ],
    }
    renderWithProviders(<NycEnforcementSection nycEnforcement={data} />)
    // Expand the card
    fireEvent.click(screen.getByText('NYC Enforcement'))
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('$15,000')).toBeInTheDocument()
    // $8,500 appears in both summary stat and detail table
    expect(screen.getAllByText('$8,500').length).toBeGreaterThanOrEqual(1)
  })

  it('renders source labels in the table', () => {
    const data = {
      summary: { record_count: 1, is_debarred: false, debarment_end_date: null, total_wages_owed: 0, total_recovered: 2000 },
      records: [
        { source: 'local_labor_law', employer_name: 'Test Cafe', debarment_start_date: '2023-03-01', amount: 2000 },
      ],
    }
    renderWithProviders(<NycEnforcementSection nycEnforcement={data} />)
    fireEvent.click(screen.getByText('NYC Enforcement'))
    expect(screen.getByText('Local Labor Law')).toBeInTheDocument()
    expect(screen.getByText('Test Cafe')).toBeInTheDocument()
  })
})
