import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { EmployerProfilePage } from '@/features/employer-profile/EmployerProfilePage'

// Mock profile hooks
vi.mock('@/shared/api/profile', async () => {
  const actual = await vi.importActual('@/shared/api/profile')
  return {
    ...actual,
    useEmployerProfile: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
    useEmployerUnifiedDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
    useScorecardDetail: vi.fn(() => ({ data: null, isLoading: false })),
  }
})

import { useEmployerProfile, useEmployerUnifiedDetail, useScorecardDetail } from '@/shared/api/profile'

function renderWithRoute(path) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/employers/:id" element={<EmployerProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('EmployerProfilePage', () => {
  beforeEach(() => {
    useEmployerProfile.mockReturnValue({ data: null, isLoading: false, isError: false })
    useEmployerUnifiedDetail.mockReturnValue({ data: null, isLoading: false, isError: false })
    useScorecardDetail.mockReturnValue({ data: null, isLoading: false })
  })

  it('shows loading skeleton while fetching', () => {
    useEmployerProfile.mockReturnValue({ data: null, isLoading: true, isError: false })

    renderWithRoute('/employers/abc123')
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders F7 employer with full profile', () => {
    useEmployerProfile.mockReturnValue({
      data: {
        employer: {
          employer_name: 'Kaiser Permanente',
          city: 'Oakland',
          state: 'CA',
          total_workers: 5000,
          naics_code: '622110',
        },
        unified_scorecard: {
          score_tier: 'Priority',
          weighted_score: 7.5,
          score_nlrb: 8.2,
          score_osha: 6.1,
          score_whd: null,
          score_contracts: 3.0,
          score_union_proximity: 5.5,
          score_financial: 4.0,
          score_size: 7.0,
          score_similarity: 6.0,
          score_industry_growth: 3.5,
        },
        osha: null,
        nlrb: null,
        cross_references: [],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRoute('/employers/abc123')
    expect(screen.getByText('Kaiser Permanente')).toBeInTheDocument()
    expect(screen.getByText('Oakland, CA')).toBeInTheDocument()
    expect(screen.getByText('7.5')).toBeInTheDocument()
    expect(screen.getByText('Priority')).toBeInTheDocument()
    expect(screen.getByText('Organizing Scorecard')).toBeInTheDocument()
  })

  it('renders non-F7 employer with basic view', () => {
    useEmployerUnifiedDetail.mockReturnValue({
      data: {
        employer: {
          participant_name: 'Amazon LLC',
          unit_city: 'Seattle',
          unit_state: 'WA',
        },
        source_type: 'NLRB',
        cross_references: [],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRoute('/employers/NLRB-12345')
    expect(screen.getByText('Amazon LLC')).toBeInTheDocument()
    expect(screen.getByText('Seattle, WA')).toBeInTheDocument()
    expect(screen.getByText(/Limited data is available/)).toBeInTheDocument()
  })

  it('shows 404 when employer not found', () => {
    useEmployerProfile.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 404, message: 'Not found' },
    })

    renderWithRoute('/employers/doesnotexist')
    expect(screen.getByText('Employer not found')).toBeInTheDocument()
  })

  it('shows generic error message', () => {
    useEmployerProfile.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 500, message: 'Internal server error' },
    })

    renderWithRoute('/employers/abc123')
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Internal server error')).toBeInTheDocument()
  })

  it('renders back button', () => {
    useEmployerProfile.mockReturnValue({ data: null, isLoading: true, isError: false })

    renderWithRoute('/employers/abc123')
    expect(screen.getByText('Back')).toBeInTheDocument()
  })
})
