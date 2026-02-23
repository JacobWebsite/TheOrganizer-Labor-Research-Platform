import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

vi.mock('@/shared/api/unions', () => ({
  useNationalUnions: vi.fn(() => ({ data: { national_unions: [] }, isLoading: false })),
  useNationalUnionDetail: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionSearch: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useUnionDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useUnionMembershipHistory: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionOrganizingCapacity: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionEmployers: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionSectors: vi.fn(() => ({ data: null })),
  useUnionAffiliations: vi.fn(() => ({ data: null })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
  useNaicsSectors: vi.fn(() => ({ data: { sectors: [] } })),
}))

import { useNationalUnions, useNationalUnionDetail, useUnionSearch } from '@/shared/api/unions'
import { AffiliationTree } from '@/features/union-explorer/AffiliationTree'
import { UnionsPage } from '@/features/union-explorer/UnionsPage'

function renderWithProviders(ui, initialEntry = '/unions') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AffiliationTree', () => {
  beforeEach(() => {
    useNationalUnions.mockReturnValue({ data: { national_unions: [] }, isLoading: false })
    useNationalUnionDetail.mockReturnValue({ data: null, isLoading: false })
    useUnionSearch.mockReturnValue({ data: null, isLoading: false, isError: false })
  })

  it('renders top-level affiliations', () => {
    const affiliations = [
      { aff_abbr: 'SEIU', name: 'Service Employees International Union', total_members: 1800000, total_locals: 150 },
      { aff_abbr: 'AFSCME', name: 'American Federation of State County and Municipal Employees', total_members: 1400000, total_locals: 120 },
    ]
    renderWithProviders(<AffiliationTree affiliations={affiliations} />)
    expect(screen.getByText('SEIU')).toBeInTheDocument()
    expect(screen.getByText('AFSCME')).toBeInTheDocument()
  })

  it('expands affiliation to show states', () => {
    useNationalUnionDetail.mockReturnValue({
      data: {
        by_state: [
          { state: 'CA', local_count: 20, total_members: 50000 },
          { state: 'NY', local_count: 15, total_members: 40000 },
        ],
      },
      isLoading: false,
    })
    const affiliations = [
      { aff_abbr: 'SEIU', name: 'Service Employees', total_members: 90000, total_locals: 35 },
    ]
    renderWithProviders(<AffiliationTree affiliations={affiliations} />)
    fireEvent.click(screen.getByText('SEIU'))
    expect(screen.getByText('CA')).toBeInTheDocument()
    expect(screen.getByText('NY')).toBeInTheDocument()
  })

  it('expands state to show locals', () => {
    useNationalUnionDetail.mockReturnValue({
      data: {
        by_state: [{ state: 'CA', local_count: 1, total_members: 5000 }],
      },
      isLoading: false,
    })
    useUnionSearch.mockReturnValue({
      data: {
        unions: [{ f_num: '123', union_name: 'SEIU Local 1000', members: 5000, city: 'Sacramento' }],
      },
      isLoading: false,
      isError: false,
    })
    const affiliations = [
      { aff_abbr: 'SEIU', name: 'Service Employees', total_members: 5000, total_locals: 1 },
    ]
    renderWithProviders(<AffiliationTree affiliations={affiliations} />)
    fireEvent.click(screen.getByText('SEIU'))
    fireEvent.click(screen.getByText('CA'))
    expect(screen.getByText('SEIU Local 1000')).toBeInTheDocument()
  })

  it('shows empty state when no affiliations', () => {
    renderWithProviders(<AffiliationTree affiliations={[]} />)
    expect(screen.getByText('No affiliation data available')).toBeInTheDocument()
  })

  it('UnionsPage renders tree/list toggle buttons', () => {
    useNationalUnions.mockReturnValue({
      data: { national_unions: [{ aff_abbr: 'SEIU', name: 'SEIU', total_members: 100, local_count: 1 }] },
      isLoading: false,
    })
    useUnionSearch.mockReturnValue({ data: { total: 0, unions: [] }, isLoading: false, isError: false })
    renderWithProviders(<UnionsPage />)
    expect(screen.getByText('List View')).toBeInTheDocument()
    expect(screen.getByText('Tree View')).toBeInTheDocument()
  })
})
