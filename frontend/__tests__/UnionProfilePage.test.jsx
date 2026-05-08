import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { UnionProfilePage } from '@/features/union-explorer/UnionProfilePage'

// Mock react-router-dom useParams
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams: vi.fn(() => ({ fnum: '518377' })),
  }
})

// Mock API hooks
vi.mock('@/shared/api/unions', () => ({
  useUnionDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useUnionMembershipHistory: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionOrganizingCapacity: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionEmployers: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionDisbursements: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionHealth: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionAssets: vi.fn(() => ({ data: null, isLoading: false })),
}))

import {
  useUnionDetail,
  useUnionMembershipHistory,
  useUnionOrganizingCapacity,
  useUnionEmployers,
  useUnionDisbursements,
  useUnionHealth,
} from '@/shared/api/unions'

const MOCK_DETAIL = {
  union: { f_num: '518377', union_name: 'SEIU Local 1199', aff_abbr: 'SEIU', sector: 'Private', city: 'New York', state: 'NY', members: 45000, employer_count: 120 },
  top_employers: [{ f7_employer_id: 'abc123', employer_name: 'NYC Health', city: 'New York', state: 'NY', workers: 5000 }],
  nlrb_elections: { summary: { wins: 10, losses: 3, win_rate: 0.77 }, elections: [] },
  financial_trends: [{ year: 2024, members: 45000, assets: 5000000, receipts: 2000000 }],
  sister_locals: [{ f_num: '518378', union_name: 'SEIU Local 32BJ', city: 'New York', state: 'NY', members: 85000 }],
  nlrb_summary: { total_elections: 13, wins: 10, losses: 3 },
}

const MOCK_MEMBERSHIP = {
  history: [
    { year: 2015, members: 38000 }, { year: 2016, members: 39000 }, { year: 2017, members: 40000 },
    { year: 2018, members: 41000 }, { year: 2019, members: 42000 }, { year: 2020, members: 41500 },
    { year: 2021, members: 43000 }, { year: 2022, members: 44000 }, { year: 2023, members: 44500 },
    { year: 2024, members: 45000 },
  ],
  trend: 'growing',
  change_pct: 18.4,
  peak_year: 2024,
  peak_members: 45000,
}

const MOCK_CAPACITY = {
  organizing_spend_share: 0.15,
  total_disbursements: 3500000,
  trend: 'increasing',
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/unions/518377']}>
        <UnionProfilePage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('UnionProfilePage', () => {
  beforeEach(() => {
    useUnionDetail.mockReturnValue({ data: null, isLoading: false, isError: false })
    useUnionMembershipHistory.mockReturnValue({ data: null, isLoading: false })
    useUnionOrganizingCapacity.mockReturnValue({ data: null, isLoading: false })
    useUnionEmployers.mockReturnValue({ data: null, isLoading: false })
    useUnionDisbursements.mockReturnValue({ data: null, isLoading: false })
    useUnionHealth.mockReturnValue({ data: null, isLoading: false })
  })

  it('shows loading skeleton while fetching', () => {
    useUnionDetail.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderPage()
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders header with union name', () => {
    useUnionDetail.mockReturnValue({ data: MOCK_DETAIL, isLoading: false, isError: false })
    renderPage()
    expect(screen.getByText('SEIU Local 1199')).toBeInTheDocument()
    // Affiliation path shown in hero banner (e.g. "SEIU > Private")
    expect(screen.getByText('SEIU > Private')).toBeInTheDocument()
  })

  it('renders membership bars', () => {
    useUnionDetail.mockReturnValue({ data: MOCK_DETAIL, isLoading: false, isError: false })
    useUnionMembershipHistory.mockReturnValue({ data: MOCK_MEMBERSHIP, isLoading: false })
    renderPage()
    expect(screen.getByText('Membership History')).toBeInTheDocument()
    expect(screen.getByText('Growing')).toBeInTheDocument()
    expect(screen.getByText('+18.4%')).toBeInTheDocument()
  })

  it('shows 404 on error', () => {
    useUnionDetail.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 404, message: 'Not found' },
    })
    renderPage()
    expect(screen.getByText('Union not found')).toBeInTheDocument()
  })

  it('renders back link', () => {
    useUnionDetail.mockReturnValue({ data: MOCK_DETAIL, isLoading: false, isError: false })
    renderPage()
    expect(screen.getByText('Back to Unions')).toBeInTheDocument()
  })

  it('shows inactive banner for stale union', () => {
    const inactiveDetail = {
      ...MOCK_DETAIL,
      union: { ...MOCK_DETAIL.union, is_likely_inactive: true, yr_covered: 2019 },
    }
    useUnionDetail.mockReturnValue({ data: inactiveDetail, isLoading: false, isError: false })
    renderPage()
    expect(screen.getByText(/Likely Inactive/)).toBeInTheDocument()
    expect(screen.getByText(/2019/)).toBeInTheDocument()
  })

  it('renders elections section', () => {
    useUnionDetail.mockReturnValue({ data: MOCK_DETAIL, isLoading: false, isError: false })
    renderPage()
    expect(screen.getByText('NLRB Elections')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument() // wins
    expect(screen.getByText('3')).toBeInTheDocument() // losses
    expect(screen.getByText('77%')).toBeInTheDocument() // win rate
  })
})
