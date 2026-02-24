import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { ResearchPage } from '@/features/research/ResearchPage'

// Mock API hooks
vi.mock('@/shared/api/research', () => ({
  useResearchRuns: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useStartResearch: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
}))

import { useResearchRuns, useStartResearch } from '@/shared/api/research'

const MOCK_RUNS = {
  runs: [
    {
      id: 1,
      company_name: 'Amazon',
      employer_id: null,
      industry_naics: '493110',
      company_type: 'public',
      status: 'completed',
      started_at: '2026-02-23T10:00:00Z',
      completed_at: '2026-02-23T10:01:30Z',
      duration_seconds: 90,
      sections_filled: 7,
      total_facts_found: 32,
      overall_quality_score: 7.5,
      progress_pct: 100,
      current_step: 'Done',
    },
    {
      id: 2,
      company_name: 'Starbucks',
      employer_id: 'abc123',
      industry_naics: '722515',
      company_type: 'public',
      status: 'running',
      started_at: '2026-02-23T10:05:00Z',
      completed_at: null,
      duration_seconds: null,
      sections_filled: 3,
      total_facts_found: 15,
      overall_quality_score: null,
      progress_pct: 45,
      current_step: 'Querying OSHA data...',
    },
    {
      id: 3,
      company_name: 'Walmart',
      employer_id: null,
      industry_naics: '452311',
      company_type: 'public',
      status: 'failed',
      started_at: '2026-02-23T09:00:00Z',
      completed_at: '2026-02-23T09:00:05Z',
      duration_seconds: 5,
      sections_filled: 0,
      total_facts_found: 0,
      overall_quality_score: null,
      progress_pct: 0,
      current_step: 'FAILED: API error',
    },
  ],
  total: 3,
  limit: 20,
  offset: 0,
}

function renderPage(initialEntry = '/research') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ResearchPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ResearchPage', () => {
  beforeEach(() => {
    useResearchRuns.mockReturnValue({ data: null, isLoading: false, isError: false })
    useStartResearch.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false })
  })

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Research Deep Dives')).toBeInTheDocument()
  })

  it('renders New Research button', () => {
    renderPage()
    expect(screen.getByText('New Research')).toBeInTheDocument()
  })

  it('shows loading skeleton when data is loading', () => {
    useResearchRuns.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderPage()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows error message on API failure', () => {
    useResearchRuns.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { message: 'Connection refused' },
    })
    renderPage()
    expect(screen.getByText(/Connection refused/)).toBeInTheDocument()
  })

  it('shows empty state when no runs exist', () => {
    useResearchRuns.mockReturnValue({
      data: { runs: [], total: 0, limit: 20, offset: 0 },
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('No research runs found')).toBeInTheDocument()
  })

  it('renders table with run data', () => {
    useResearchRuns.mockReturnValue({
      data: MOCK_RUNS,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('Amazon')).toBeInTheDocument()
    expect(screen.getByText('Starbucks')).toBeInTheDocument()
    expect(screen.getByText('Walmart')).toBeInTheDocument()
  })

  it('shows run count', () => {
    useResearchRuns.mockReturnValue({
      data: MOCK_RUNS,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('3 runs found')).toBeInTheDocument()
  })

  it('shows status badges', () => {
    useResearchRuns.mockReturnValue({
      data: MOCK_RUNS,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText(/running/)).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('opens new research modal on button click', () => {
    renderPage()
    fireEvent.click(screen.getAllByText('New Research')[0])
    expect(screen.getByText('New Research Deep Dive')).toBeInTheDocument()
    expect(screen.getByText('Company Name *')).toBeInTheDocument()
  })

  it('renders help section', () => {
    renderPage()
    expect(screen.getByText('How to read this page')).toBeInTheDocument()
  })
})
