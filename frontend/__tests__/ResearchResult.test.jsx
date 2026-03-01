import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { ResearchResultPage } from '@/features/research/ResearchResultPage'

// Mock API hooks
vi.mock('@/shared/api/research', () => ({
  useResearchStatus: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useResearchResult: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useStartResearch: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false })),
  useReviewFact: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useReviewSummary: vi.fn(() => ({ data: null, isLoading: false })),
  useSetHumanScore: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSetRunUsefulness: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useFlagFact: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAutoConfirmFacts: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useReviewSection: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  usePriorityFacts: vi.fn(() => ({ data: null, isLoading: false })),
}))

import { useResearchStatus, useResearchResult } from '@/shared/api/research'

const MOCK_STATUS_RUNNING = {
  id: 1,
  company_name: 'Amazon',
  status: 'running',
  current_step: 'Querying OSHA violations...',
  progress_pct: 45,
  started_at: '2026-02-23T10:00:00Z',
  completed_at: null,
  duration_seconds: null,
  total_tools_called: 5,
  total_facts_found: 12,
  sections_filled: 3,
}

const MOCK_STATUS_COMPLETED = {
  id: 1,
  company_name: 'Amazon',
  status: 'completed',
  current_step: 'Done',
  progress_pct: 100,
  started_at: '2026-02-23T10:00:00Z',
  completed_at: '2026-02-23T10:01:30Z',
  duration_seconds: 90,
  total_tools_called: 12,
  total_facts_found: 32,
  sections_filled: 7,
}

const MOCK_STATUS_FAILED = {
  id: 2,
  company_name: 'TestCorp',
  status: 'failed',
  current_step: 'FAILED: Gemini API timeout',
  progress_pct: 10,
  started_at: '2026-02-23T09:00:00Z',
  completed_at: '2026-02-23T09:00:05Z',
  duration_seconds: 5,
  total_tools_called: 1,
  total_facts_found: 0,
  sections_filled: 0,
}

const MOCK_RESULT = {
  run_id: 1,
  company_name: 'Amazon',
  status: 'completed',
  duration_seconds: 90,
  sections_filled: 7,
  total_facts: 32,
  dossier: {
    dossier: {
      identity: { legal_name: 'Amazon.com Inc.', company_type: 'public' },
      labor: { union_names: ['Teamsters', 'ALU'], nlrb_election_count: 15 },
      assessment: { organizing_summary: 'Active NLRB cases and recent organizing campaigns.' },
      workplace: { osha_violation_count: 23 },
    },
  },
  facts_by_section: {
    identity: [
      { attribute_name: 'legal_name', display_name: 'Legal Name', attribute_value: 'Amazon.com Inc.', source_name: 'SEC', confidence: 0.95, as_of_date: '2026-01' },
      { attribute_name: 'naics', display_name: 'Industry', attribute_value: '493110 - Warehousing', source_name: 'OSHA', confidence: 0.9, as_of_date: '2025-12' },
    ],
    labor: [
      { attribute_name: 'nlrb_elections', display_name: 'NLRB Elections', attribute_value: '15', source_name: 'NLRB', confidence: 0.85, as_of_date: '2026-02' },
    ],
    assessment: [
      { attribute_name: 'organizing_potential', display_name: 'Organizing Potential', attribute_value: 'High', source_name: 'Analysis', confidence: 0.7 },
    ],
  },
  action_log: [
    { tool_name: 'lookup_employer', execution_order: 1, data_found: true, facts_extracted: 5, latency_ms: 120, result_summary: 'Found employer record' },
    { tool_name: 'query_osha', execution_order: 2, data_found: true, facts_extracted: 8, latency_ms: 350, result_summary: '23 violations found' },
    { tool_name: 'query_nlrb', execution_order: 3, data_found: true, facts_extracted: 3, latency_ms: 200, result_summary: '15 elections, 4 ULPs' },
    { tool_name: 'query_sec', execution_order: 4, data_found: false, facts_extracted: 0, latency_ms: 150, result_summary: 'No SEC filings matched' },
  ],
  quality_score: 7.5,
  quality_dimensions: {
    coverage: 8.0,
    source_quality: 7.2,
    consistency: 9.0,
    freshness: 6.5,
    efficiency: 8.0,
  },
}

function renderResultPage(runId = '1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/research/${runId}`]}>
        <Routes>
          <Route path="/research/:runId" element={<ResearchResultPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ResearchResultPage', () => {
  beforeEach(() => {
    useResearchStatus.mockReturnValue({ data: null, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: null, isLoading: false, isError: false })
  })

  it('shows loading skeleton on initial load', () => {
    useResearchStatus.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderResultPage()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows back button', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_RUNNING, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('Back')).toBeInTheDocument()
  })

  it('shows company name in header', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_RUNNING, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('Amazon')).toBeInTheDocument()
  })

  it('shows progress bar and current step for running state', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_RUNNING, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('Querying OSHA violations...')).toBeInTheDocument()
  })

  it('shows status indicator for running state', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_RUNNING, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('shows metadata grid for completed state', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('1m 30s')).toBeInTheDocument() // duration
    expect(screen.getByText('32')).toBeInTheDocument() // total facts
    expect(screen.getByText('7/7')).toBeInTheDocument() // sections
    expect(screen.getByText('12')).toBeInTheDocument() // tools called
  })

  it('renders dossier sections for completed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    // Section titles now include item counts (e.g. "Company Identity (4)")
    expect(screen.getByText(/Company Identity/)).toBeInTheDocument()
    expect(screen.getByText(/Labor Relations/)).toBeInTheDocument()
    expect(screen.getByText(/Overall Assessment/)).toBeInTheDocument()
  })

  it('renders quality score for completed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('7.5')).toBeInTheDocument()
    expect(screen.getByText('Research Quality')).toBeInTheDocument()
  })

  it('renders quality dimension bars for completed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText(/Coverage/)).toBeInTheDocument()
    expect(screen.getByText(/Source Quality/)).toBeInTheDocument()
    expect(screen.getByText(/Consistency/)).toBeInTheDocument()
    expect(screen.getByText(/Freshness/)).toBeInTheDocument()
    expect(screen.getByText(/Efficiency/)).toBeInTheDocument()
  })

  it('renders action log for completed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('Action Log')).toBeInTheDocument()
  })

  it('shows failure message for failed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_FAILED, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText(/Gemini API timeout/)).toBeInTheDocument()
  })

  it('shows 404 when run not found', () => {
    useResearchStatus.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 404, message: 'Not found' },
    })
    renderResultPage('999')
    expect(screen.getByText('Research run not found')).toBeInTheDocument()
  })

  it('shows Run Again button for completed run', () => {
    useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
    useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
    renderResultPage()
    expect(screen.getByText('Run Again')).toBeInTheDocument()
  })
})
