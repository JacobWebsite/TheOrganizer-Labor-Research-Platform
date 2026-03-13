import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

vi.mock('@/shared/api/unions', () => ({
  useNationalUnions: vi.fn(() => ({ data: { national_unions: [] }, isLoading: false })),
  useNationalUnionDetail: vi.fn(() => ({ data: null, isLoading: false })),
  useUnionHierarchy: vi.fn(() => ({ data: null, isLoading: false })),
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

import { useNationalUnions, useNationalUnionDetail, useUnionHierarchy, useUnionSearch } from '@/shared/api/unions'
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
    useUnionHierarchy.mockReturnValue({ data: null, isLoading: false })
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

  it('expands affiliation to show states from hierarchy', () => {
    useUnionHierarchy.mockReturnValue({
      data: {
        affiliation: 'SEIU',
        national: null,
        intermediates: [],
        unaffiliated_locals: {
          by_state: {
            CA: [{ f_num: '123', name: 'SEIU Local 1000', members: 50000, city: 'Sacramento', state: 'CA' }],
            NY: [{ f_num: '456', name: 'SEIU Local 32BJ', members: 40000, city: 'New York', state: 'NY' }],
          },
        },
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

  it('expands state to show locals from hierarchy', () => {
    useUnionHierarchy.mockReturnValue({
      data: {
        affiliation: 'SEIU',
        national: null,
        intermediates: [],
        unaffiliated_locals: {
          by_state: {
            CA: [{ f_num: '123', name: 'SEIU Local 1000', members: 5000, city: 'Sacramento', state: 'CA' }],
          },
        },
      },
      isLoading: false,
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

  it('shows inactive label for stale locals', () => {
    useUnionHierarchy.mockReturnValue({
      data: {
        affiliation: 'IBT',
        national: null,
        intermediates: [],
        unaffiliated_locals: {
          by_state: {
            OH: [{ f_num: '999', name: 'Teamsters Local 99', members: 200, city: 'Cleveland', state: 'OH', is_likely_inactive: true }],
          },
        },
      },
      isLoading: false,
    })
    const affiliations = [
      { aff_abbr: 'IBT', name: 'Teamsters', total_members: 200, total_locals: 1 },
    ]
    renderWithProviders(<AffiliationTree affiliations={affiliations} />)
    fireEvent.click(screen.getByText('IBT'))
    fireEvent.click(screen.getByText('OH'))
    expect(screen.getByText('(Inactive)')).toBeInTheDocument()
  })

  it('renders intermediate nodes with level labels', () => {
    useUnionHierarchy.mockReturnValue({
      data: {
        affiliation: 'CJA',
        national: null,
        intermediates: [
          {
            f_num: '500', name: 'Carpenters DC of Greater NY', level_code: 'DC',
            members: 25000, city: 'New York', state: 'NY',
            is_likely_inactive: false, locals_count: 12,
            locals: [
              { f_num: '501', name: 'Carpenters Local 157', members: 3000, city: 'New York', state: 'NY', is_likely_inactive: false },
            ],
          },
        ],
        unaffiliated_locals: { by_state: {} },
      },
      isLoading: false,
    })
    const affiliations = [
      { aff_abbr: 'CJA', name: 'Carpenters', total_members: 25000, total_locals: 50 },
    ]
    renderWithProviders(<AffiliationTree affiliations={affiliations} />)
    fireEvent.click(screen.getByText('CJA'))
    expect(screen.getByText('Carpenters DC of Greater NY')).toBeInTheDocument()
    expect(screen.getByText('(District Council)')).toBeInTheDocument()
    expect(screen.getByText('12 locals')).toBeInTheDocument()
  })

  it('UnionsPage renders tree/list toggle buttons', () => {
    useNationalUnions.mockReturnValue({
      data: { national_unions: [{ aff_abbr: 'SEIU', name: 'SEIU', total_members: 100, local_count: 1 }] },
      isLoading: false,
    })
    useUnionSearch.mockReturnValue({ data: { total: 0, unions: [] }, isLoading: false, isError: false })
    renderWithProviders(<UnionsPage />)
    expect(screen.getByText('List')).toBeInTheDocument()
    expect(screen.getByText('Tree')).toBeInTheDocument()
  })
})
