import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { TargetsPage } from '@/features/scorecard/TargetsPage'

// Mock API hooks
vi.mock('@/shared/api/targets', () => ({
  useNonUnionTargets: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useTargetStats: vi.fn(() => ({ data: null, isLoading: false })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
  useNaicsSectors: vi.fn(() => ({ data: { sectors: [] } })),
}))

import { useNonUnionTargets, useTargetStats } from '@/shared/api/targets'

const MOCK_STATS = {
  total: 2500000,
  by_source_origin: [
    { source_origin: 'bmf', cnt: 2000000 },
    { source_origin: 'sam', cnt: 400000 },
  ],
  top_states: [{ state: 'CA', cnt: 200000 }],
  flags: { union_true: 100000, nonprofit_true: 500000, contractor_true: 80000, labor_org_true: 5000 },
  quality_distribution: [
    { tier: '0-20', cnt: 1000000 },
    { tier: '21-40', cnt: 800000 },
    { tier: '41-60', cnt: 500000 },
    { tier: '61-80', cnt: 150000 },
    { tier: '81-100', cnt: 50000 },
  ],
  avg_source_count: 1.2,
}

const MOCK_RESULTS = {
  total: 3,
  page: 1,
  pages: 1,
  results: [
    { id: 1, display_name: 'Acme Corp', city: 'NYC', state: 'NY', naics: '44', employee_count: 500, is_federal_contractor: true, is_nonprofit: false, source_origin: 'sam', data_quality_score: 75, source_count: 3 },
    { id: 2, display_name: 'Beta LLC', city: 'LA', state: 'CA', naics: '62', employee_count: null, is_federal_contractor: false, is_nonprofit: true, source_origin: 'bmf', data_quality_score: 35, source_count: 1 },
    { id: 3, display_name: 'Gamma Inc', city: 'Chicago', state: 'IL', naics: '23', employee_count: 1200, is_federal_contractor: false, is_nonprofit: false, source_origin: 'mergent', data_quality_score: 90, source_count: 5 },
  ],
}

function renderWithRoute(initialEntry = '/targets') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <TargetsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('TargetsPage', () => {
  beforeEach(() => {
    useNonUnionTargets.mockReturnValue({ data: null, isLoading: false, isError: false })
    useTargetStats.mockReturnValue({ data: null, isLoading: false })
  })

  it('renders page title', () => {
    renderWithRoute()
    expect(screen.getByText('Organizing Targets')).toBeInTheDocument()
  })

  it('shows stats card when stats load', () => {
    useTargetStats.mockReturnValue({ data: MOCK_STATS, isLoading: false })
    renderWithRoute()
    expect(screen.getByText('2,500,000')).toBeInTheDocument() // total
    expect(screen.getByText('80,000')).toBeInTheDocument() // contractors
  })

  it('shows loading skeleton when data is loading', () => {
    useNonUnionTargets.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderWithRoute()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows error message on API failure', () => {
    useNonUnionTargets.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { message: 'Database timeout' },
    })
    renderWithRoute()
    expect(screen.getByText(/Database timeout/)).toBeInTheDocument()
  })

  it('shows empty state when no results', () => {
    useNonUnionTargets.mockReturnValue({
      data: { total: 0, page: 1, pages: 0, results: [] },
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('No targets found')).toBeInTheDocument()
  })

  it('renders table with data', () => {
    useNonUnionTargets.mockReturnValue({
      data: MOCK_RESULTS,
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Beta LLC')).toBeInTheDocument()
    expect(screen.getByText('Gamma Inc')).toBeInTheDocument()
  })

  it('shows result count', () => {
    useNonUnionTargets.mockReturnValue({
      data: MOCK_RESULTS,
      isLoading: false,
      isError: false,
    })
    renderWithRoute()
    expect(screen.getByText('3 targets found')).toBeInTheDocument()
  })

  it('initializes filters from URL params', () => {
    useNonUnionTargets.mockReturnValue({
      data: MOCK_RESULTS,
      isLoading: false,
      isError: false,
    })
    renderWithRoute('/targets?q=acme&state=NY')
    // The search input should have the value from URL
    const input = screen.getByPlaceholderText('Search employers...')
    expect(input.value).toBe('acme')
  })
})
