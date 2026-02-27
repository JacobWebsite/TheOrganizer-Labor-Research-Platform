import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { ResearchInsightsCard } from '@/features/employer-profile/ResearchInsightsCard'

// Mock the research API hook
vi.mock('@/shared/api/research', () => ({
  useResearchResult: vi.fn(() => ({ data: null, isLoading: false })),
}))

function renderWithQuery(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  )
}

const mockScorecard = {
  has_research: true,
  research_run_id: 42,
  research_quality: 7.8,
  research_approach: 'Bottom-up organizing through safety committee',
  research_trend: 'Revenue declining 5% YoY since 2024',
  research_contradictions: [
    { field: 'employee_count', db_value: 500, web_value: 750 },
    { field: 'naics_code', db_value: '622110', web_value: '621610' },
  ],
  strategic_delta: 1.25,
}

describe('ResearchInsightsCard', () => {
  it('renders null when no research data', () => {
    const { container } = renderWithQuery(<ResearchInsightsCard scorecard={{ has_research: false }} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders null when scorecard is null', () => {
    const { container } = renderWithQuery(<ResearchInsightsCard scorecard={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows research quality score', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('Research Insights')).toBeInTheDocument()
    expect(screen.getByText('7.8')).toBeInTheDocument()
    expect(screen.getByText('Good')).toBeInTheDocument()
  })

  it('shows recommended approach', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('Recommended Approach')).toBeInTheDocument()
    expect(screen.getByText('Bottom-up organizing through safety committee')).toBeInTheDocument()
  })

  it('shows financial trend', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('Financial Trend')).toBeInTheDocument()
    expect(screen.getByText('Revenue declining 5% YoY since 2024')).toBeInTheDocument()
  })

  it('shows contradictions', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('Source Contradictions (2)')).toBeInTheDocument()
    expect(screen.getByText('employee count')).toBeInTheDocument()
  })

  it('shows score delta', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('+1.25')).toBeInTheDocument()
  })

  it('shows view dossier button', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('View Full Research Dossier')).toBeInTheDocument()
  })

  it('shows run ID', () => {
    renderWithQuery(<ResearchInsightsCard scorecard={mockScorecard} />)
    expect(screen.getByText('#42')).toBeInTheDocument()
  })
})
