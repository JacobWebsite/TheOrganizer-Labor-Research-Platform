import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { UnifiedScorecardPage } from '@/features/scorecard/UnifiedScorecardPage'

// Mock API hooks
vi.mock('@/shared/api/scorecard', () => ({
  useUnifiedScorecard: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useUnifiedScorecardStats: vi.fn(() => ({ data: null, isLoading: false })),
  useUnifiedScorecardStates: vi.fn(() => ({ data: [], isLoading: false })),
  buildExportUrl: vi.fn(() => 'http://localhost:8001/api/scorecard/unified/export'),
}))

import { useUnifiedScorecard, useUnifiedScorecardStats } from '@/shared/api/scorecard'

const MOCK_STATS = {
  overview: {
    total_employers: 146863,
    avg_score: 5.36,
    avg_factors: 3.1,
  },
  tier_distribution: [
    { score_tier: 'Priority', cnt: 2964 },
    { score_tier: 'Strong', cnt: 15590 },
    { score_tier: 'Promising', cnt: 40184 },
    { score_tier: 'Moderate', cnt: 51343 },
    { score_tier: 'Low', cnt: 36782 },
  ],
}

const MOCK_DATA = {
  data: [
    {
      employer_id: 'E001',
      employer_name: 'Test Corp',
      state: 'NY',
      city: 'New York',
      weighted_score: 8.5,
      score_tier: 'Priority',
      factors_available: 7,
      factors_total: 10,
      score_osha: 6.2,
      score_nlrb: 8.0,
      score_whd: 5.1,
      recommended_action: 'PURSUE NOW',
      has_compound_enforcement: true,
      has_close_election: false,
      has_child_labor: false,
      is_whd_repeat_violator: false,
    },
    {
      employer_id: 'E002',
      employer_name: 'Low Data Inc',
      state: 'CA',
      city: 'Los Angeles',
      weighted_score: 3.2,
      score_tier: 'Moderate',
      factors_available: 2,
      factors_total: 10,
      score_osha: null,
      score_nlrb: null,
      score_whd: null,
      recommended_action: 'INSUFFICIENT DATA',
      has_compound_enforcement: false,
      has_close_election: false,
      has_child_labor: false,
      is_whd_repeat_violator: false,
    },
  ],
  total: 2,
  offset: 0,
  page_size: 50,
  has_more: false,
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/scorecard']}>
        <UnifiedScorecardPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('UnifiedScorecardPage', () => {
  beforeEach(() => {
    useUnifiedScorecard.mockReturnValue({ data: null, isLoading: false, isError: false })
    useUnifiedScorecardStats.mockReturnValue({ data: null, isLoading: false })
  })

  it('renders page title', () => {
    renderPage()
    expect(screen.getByText('Union Reference Scorecard')).toBeInTheDocument()
  })

  it('shows stats when loaded', () => {
    useUnifiedScorecardStats.mockReturnValue({ data: MOCK_STATS, isLoading: false })
    renderPage()
    expect(screen.getByText('146,863')).toBeInTheDocument()
  })

  it('shows empty state when no results', () => {
    useUnifiedScorecard.mockReturnValue({
      data: { data: [], total: 0, offset: 0, page_size: 50, has_more: false },
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('No employers found')).toBeInTheDocument()
  })

  it('shows error message on API failure', () => {
    useUnifiedScorecard.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { message: 'Server error' },
    })
    renderPage()
    expect(screen.getByText(/Server error/)).toBeInTheDocument()
  })

  it('renders table rows with data', () => {
    useUnifiedScorecard.mockReturnValue({
      data: MOCK_DATA,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('Test Corp')).toBeInTheDocument()
    expect(screen.getByText('Low Data Inc')).toBeInTheDocument()
  })

  it('shows low-data amber badge for <3 factors', () => {
    useUnifiedScorecard.mockReturnValue({
      data: MOCK_DATA,
      isLoading: false,
      isError: false,
    })
    const { container } = renderPage()
    // Low Data Inc has factors_available=2, should show amber badge
    expect(container.innerHTML).toContain('Low Data')
    expect(container.innerHTML).toContain('bg-amber-100')
  })

  it('shows result count', () => {
    useUnifiedScorecard.mockReturnValue({
      data: MOCK_DATA,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('2 employers found')).toBeInTheDocument()
  })

  it('shows compound enforcement flag badge', () => {
    useUnifiedScorecard.mockReturnValue({
      data: MOCK_DATA,
      isLoading: false,
      isError: false,
    })
    const { container } = renderPage()
    expect(container.innerHTML).toContain('Compound')
  })

  it('renders export CSV button', () => {
    useUnifiedScorecard.mockReturnValue({
      data: MOCK_DATA,
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('Export CSV')).toBeInTheDocument()
  })
})
