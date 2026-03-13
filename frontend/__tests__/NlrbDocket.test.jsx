import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { NlrbSection } from '@/features/employer-profile/NlrbSection'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const baseNlrb = {
  summary: { total_elections: 2, wins: 1, losses: 1, total_ulp_cases: 0 },
  elections: [
    { case_number: '01-RC-100001', election_date: '2024-06-15', result: 'Won', voters_eligible: 50, union_name: 'SEIU' },
    { case_number: '01-RC-100002', election_date: '2023-01-10', result: 'Lost', voters_eligible: 30, union_name: 'CWA' },
  ],
  ulp_cases: [],
}

const docketWithRecent = {
  summary: {
    cases_with_docket: 3,
    total_entries: 42,
    has_recent_activity: true,
    most_recent_date: '2025-12-01',
  },
  cases: [
    { case_number: '05-RC-400001', first_activity: '2024-01-01', last_activity: '2025-12-01', entry_count: 20, duration_days: 700, is_recent: true },
    { case_number: '05-RC-400002', first_activity: '2022-03-15', last_activity: '2023-06-30', entry_count: 12, duration_days: 472, is_recent: false },
    { case_number: '05-RC-400003', first_activity: '2021-05-01', last_activity: '2021-08-15', entry_count: 10, duration_days: 106, is_recent: false },
  ],
}

const docketNoRecent = {
  summary: {
    cases_with_docket: 1,
    total_entries: 5,
    has_recent_activity: false,
    most_recent_date: '2020-06-01',
  },
  cases: [
    { case_number: '01-RC-200001', first_activity: '2020-01-01', last_activity: '2020-06-01', entry_count: 5, duration_days: 152, is_recent: false },
  ],
}

describe('NlrbSection - Docket Activity', () => {
  it('renders nothing for docket when docket prop is null', () => {
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={null} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(screen.queryByText('Docket Activity')).not.toBeInTheDocument()
  })

  it('renders nothing for docket when docket has zero cases', () => {
    const emptyDocket = {
      summary: { cases_with_docket: 0, total_entries: 0, has_recent_activity: false, most_recent_date: null },
      cases: [],
    }
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={emptyDocket} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(screen.queryByText('Docket Activity')).not.toBeInTheDocument()
  })

  it('renders docket summary line and Active badge when has_recent_activity', () => {
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={docketWithRecent} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(screen.getByText('Docket Activity')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText(/3 cases with docket data/)).toBeInTheDocument()
  })

  it('does not show Active badge when has_recent_activity is false', () => {
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={docketNoRecent} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    expect(screen.getByText('Docket Activity')).toBeInTheDocument()
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
    expect(screen.getByText(/1 case with docket data/)).toBeInTheDocument()
  })

  it('renders docket table with case rows', () => {
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={docketWithRecent} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    // Table headers
    expect(screen.getByText('First Activity')).toBeInTheDocument()
    expect(screen.getByText('Last Activity')).toBeInTheDocument()
    // Case numbers should appear in docket table
    expect(screen.getByText('05-RC-400001')).toBeInTheDocument()
    expect(screen.getByText('05-RC-400002')).toBeInTheDocument()
    expect(screen.getByText('05-RC-400003')).toBeInTheDocument()
    // Recent / Inactive badges
    expect(screen.getByText('Recent')).toBeInTheDocument()
    expect(screen.getAllByText('Inactive').length).toBe(2)
  })

  it('shows expand button when more than 5 docket cases', () => {
    const manyDocket = {
      summary: { cases_with_docket: 7, total_entries: 100, has_recent_activity: false, most_recent_date: '2024-01-01' },
      cases: Array.from({ length: 7 }, (_, i) => ({
        case_number: `01-RC-30000${i}`,
        first_activity: '2023-01-01',
        last_activity: '2024-01-01',
        entry_count: 10 + i,
        duration_days: 365,
        is_recent: false,
      })),
    }
    renderWithProviders(<NlrbSection nlrb={baseNlrb} docket={manyDocket} />)
    fireEvent.click(screen.getByText('NLRB Activity'))
    // Only first 5 rows visible initially
    expect(screen.getByText('01-RC-300000')).toBeInTheDocument()
    expect(screen.getByText('01-RC-300004')).toBeInTheDocument()
    expect(screen.queryByText('01-RC-300005')).not.toBeInTheDocument()
    // Expand button present
    const expandBtn = screen.getByText('Show all 7 cases')
    expect(expandBtn).toBeInTheDocument()
    // Click to expand
    fireEvent.click(expandBtn)
    expect(screen.getByText('01-RC-300005')).toBeInTheDocument()
    expect(screen.getByText('01-RC-300006')).toBeInTheDocument()
    // Now shows "Show less"
    expect(screen.getByText('Show less')).toBeInTheDocument()
  })
})
