import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CompareEmployersPage } from '@/features/scorecard/CompareEmployersPage'

vi.mock('@/shared/api/profile', () => ({
  parseCanonicalId: vi.fn((id) => {
    if (!id) return { isF7: false, sourceType: 'UNKNOWN', rawId: id }
    const prefixMatch = id.match(/^(NLRB|VR|MANUAL|MASTER)-(.+)$/)
    if (prefixMatch) {
      return { isF7: false, sourceType: prefixMatch[1], rawId: prefixMatch[2] }
    }
    return { isF7: true, sourceType: 'F7', rawId: id }
  }),
  useScorecardDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
}))

vi.mock('@/shared/api/targets', () => ({
  useNonUnionTargets: vi.fn(() => ({ data: { results: [] }, isLoading: false, isError: false })),
  useTargetScorecardDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
}))

import { useScorecardDetail } from '@/shared/api/profile'
import { useNonUnionTargets, useTargetScorecardDetail } from '@/shared/api/targets'

const EMPLOYER_A = {
  employer_id: 'ABC123',
  employer_name: 'Acme Logistics',
  state: 'WA',
  naics: '493110',
  weighted_score: 7.2,
  score_tier: 'Strong',
  factors_available: 8,
  score_osha: 6.0,
  score_nlrb: 8.5,
  score_whd: 5.0,
  score_contracts: 4.0,
  score_financial: 7.0,
  score_industry_growth: 5.5,
  score_union_proximity: 6.5,
  score_similarity: 4.5,
  score_size: 3.0,
}

const EMPLOYER_B = {
  employer_id: 'DEF456',
  employer_name: 'Northstar Foods',
  state: 'CA',
  naics: '311999',
  weighted_score: 5.4,
  score_tier: 'Promising',
  factors_available: 7,
  score_osha: 3.5,
  score_nlrb: 6.0,
  score_whd: 4.0,
  score_contracts: 2.5,
  score_financial: 5.0,
  score_industry_growth: 7.0,
  score_union_proximity: 5.0,
  score_similarity: 3.5,
  score_size: 4.0,
}

function renderPage(entry = '/compare?ids=ABC123,DEF456') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/compare" element={<CompareEmployersPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('CompareEmployersPage', () => {
  beforeEach(() => {
    useNonUnionTargets.mockReturnValue({ data: { results: [] }, isLoading: false, isError: false })
    useTargetScorecardDetail.mockReturnValue({ data: null, isLoading: false, isError: false })
    useScorecardDetail
      .mockReturnValueOnce({ data: EMPLOYER_A, isLoading: false, isError: false })
      .mockReturnValueOnce({ data: EMPLOYER_B, isLoading: false, isError: false })
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
  })

  it('renders with employer ids in the url', () => {
    renderPage()
    expect(screen.getAllByText('Acme Logistics').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Northstar Foods').length).toBeGreaterThan(0)
  })

  it('shows comparison metrics and factor scores', () => {
    renderPage()
    expect(screen.getByText('Comparison Table')).toBeInTheDocument()
    expect(screen.getAllByText('Weighted Score').length).toBeGreaterThan(0)
    expect(screen.getAllByText('OSHA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('7.2').length).toBeGreaterThan(0)
    expect(screen.getAllByText('5.4').length).toBeGreaterThan(0)
  })

  it('shows loading state gracefully', () => {
    useScorecardDetail
      .mockReset()
      .mockReturnValueOnce({ data: null, isLoading: true, isError: false })
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
    renderPage('/compare?ids=ABC123')
    expect(screen.getAllByText(/Loading/i).length).toBeGreaterThan(0)
  })

  it('shows add employer placeholder when fewer than three employers are present', () => {
    renderPage('/compare?ids=ABC123')
    expect(screen.getAllByText(/Add employer to compare/i).length).toBeGreaterThan(0)
  })

  it('shows search interface when no ids are provided', () => {
    useScorecardDetail.mockReset()
    useScorecardDetail
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
      .mockReturnValueOnce({ data: null, isLoading: false, isError: false })
    renderPage('/compare')
    expect(screen.getByRole('heading', { name: 'Add Employers' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Search non-union targets/i)).toBeInTheDocument()
  })
})
