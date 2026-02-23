import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { UnionsPage } from '@/features/union-explorer/UnionsPage'

// Mock API hooks
vi.mock('@/shared/api/unions', () => ({
  useUnionSearch: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useNationalUnions: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionSectors: vi.fn(() => ({ data: [] })),
  useUnionAffiliations: vi.fn(() => ({ data: [] })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
  useNaicsSectors: vi.fn(() => ({ data: { sectors: [] } })),
}))

import { useUnionSearch, useNationalUnions } from '@/shared/api/unions'

const MOCK_NATIONAL = [
  { aff_abbr: 'SEIU', name: 'Service Employees International Union', total_members: 1500000, local_count: 150 },
  { aff_abbr: 'AFSCME', name: 'American Federation of State County and Municipal Employees', total_members: 1300000, local_count: 120 },
]

const MOCK_RESULTS = {
  total: 2,
  unions: [
    { f_num: '518377', union_name: 'SEIU Local 1199', aff_abbr: 'SEIU', city: 'New York', state: 'NY', members: 45000, employer_count: 120, workers: 85000 },
    { f_num: '531245', union_name: 'AFSCME Local 1000', aff_abbr: 'AFSCME', city: 'Albany', state: 'NY', members: 32000, employer_count: 80, workers: 64000 },
  ],
}

function renderWithRoute(initialEntry = '/unions') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <UnionsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('UnionsPage', () => {
  beforeEach(() => {
    useUnionSearch.mockReturnValue({ data: null, isLoading: false, isError: false })
    useNationalUnions.mockReturnValue({ data: null, isLoading: false })
  })

  it('renders page title', () => {
    renderWithRoute()
    expect(screen.getByText('Union Explorer')).toBeInTheDocument()
  })

  it('shows summary card with national data', () => {
    useNationalUnions.mockReturnValue({ data: { national_unions: MOCK_NATIONAL }, isLoading: false })
    renderWithRoute()
    expect(screen.getByText('National Unions Overview')).toBeInTheDocument()
    expect(screen.getByText('270')).toBeInTheDocument() // 150 + 120 total locals
    expect(screen.getByText('2,800,000')).toBeInTheDocument() // 1.5M + 1.3M total members
  })

  it('shows loading skeleton when data is loading', () => {
    useUnionSearch.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderWithRoute()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows error message on API failure', () => {
    useUnionSearch.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { message: 'Database timeout' },
    })
    renderWithRoute()
    expect(screen.getByText(/Database timeout/)).toBeInTheDocument()
  })

  it('shows empty state when no results', () => {
    useUnionSearch.mockReturnValue({
      data: { total: 0, unions: [] },
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('No unions found')).toBeInTheDocument()
  })

  it('renders table with data', () => {
    useUnionSearch.mockReturnValue({
      data: MOCK_RESULTS,
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('SEIU Local 1199')).toBeInTheDocument()
    expect(screen.getByText('AFSCME Local 1000')).toBeInTheDocument()
  })

  it('shows result count', () => {
    useUnionSearch.mockReturnValue({
      data: MOCK_RESULTS,
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('2 unions found')).toBeInTheDocument()
  })
})
