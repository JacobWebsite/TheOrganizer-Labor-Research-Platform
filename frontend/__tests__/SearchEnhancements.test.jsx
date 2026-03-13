import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

// Mock API hooks
vi.mock('@/shared/api/employers', () => ({
  useEmployerSearch: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useEmployerAutocomplete: vi.fn(() => ({ data: null })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
  useNaicsSectors: vi.fn(() => ({ data: { sectors: [] } })),
}))

import { useEmployerSearch } from '@/shared/api/employers'
import { SearchFilters } from '@/features/search/SearchFilters'
import { SearchPage } from '@/features/search/SearchPage'
import { SearchResultCard } from '@/features/search/SearchResultCard'

const EMPTY_FILTERS = {
  state: '', naics: '', source_type: '', has_union: '',
  score_tier: '', min_workers: '', max_workers: '',
}

function renderWithProviders(ui, initialEntry = '/search') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SearchEnhancements', () => {
  beforeEach(() => {
    useEmployerSearch.mockReturnValue({ data: null, isLoading: false, isError: false })
  })

  it('renders score tier dropdown when filters expanded', () => {
    renderWithProviders(
      <SearchFilters filters={EMPTY_FILTERS} onSetFilter={() => {}} onClearFilter={() => {}} />
    )
    fireEvent.click(screen.getByText('Filters'))
    expect(screen.getByLabelText('Filter by tier')).toBeInTheDocument()
  })

  it('renders employee size filter inputs when expanded', () => {
    renderWithProviders(
      <SearchFilters filters={EMPTY_FILTERS} onSetFilter={() => {}} onClearFilter={() => {}} />
    )
    fireEvent.click(screen.getByText('Filters'))
    expect(screen.getByLabelText('Minimum workers')).toBeInTheDocument()
    expect(screen.getByLabelText('Maximum workers')).toBeInTheDocument()
  })

  it('calls onSetFilter when tier changes', () => {
    const onSet = vi.fn()
    renderWithProviders(
      <SearchFilters filters={EMPTY_FILTERS} onSetFilter={onSet} onClearFilter={() => {}} />
    )
    fireEvent.click(screen.getByText('Filters'))
    fireEvent.change(screen.getByLabelText('Filter by tier'), { target: { value: 'Priority' } })
    expect(onSet).toHaveBeenCalledWith('score_tier', 'Priority')
  })

  it('shows tier filter chip', () => {
    renderWithProviders(
      <SearchFilters
        filters={{ ...EMPTY_FILTERS, score_tier: 'Priority' }}
        onSetFilter={() => {}}
        onClearFilter={() => {}}
      />
    )
    expect(screen.getByText('Tier: Priority')).toBeInTheDocument()
  })

  it('renders SearchResultCard with employer data', () => {
    const emp = {
      canonical_id: '1', employer_name: 'Acme Corp', city: 'NYC', state: 'NY',
      unit_size: 100, source_type: 'F7', union_name: 'SEIU',
      group_member_count: null, consolidated_workers: null,
    }
    renderWithProviders(<SearchResultCard employer={emp} />)
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('NYC, NY')).toBeInTheDocument()
    expect(screen.getByText('Union: SEIU')).toBeInTheDocument()
  })

  it('renders factors badge for F7 employer with factors_available', () => {
    const emp = {
      canonical_id: '2', employer_name: 'Factor Corp', city: 'LA', state: 'CA',
      unit_size: 200, source_type: 'F7', union_name: 'UAW',
      group_member_count: null, consolidated_workers: null,
      factors_available: 7, factors_total: 10,
    }
    renderWithProviders(<SearchResultCard employer={emp} />)
    expect(screen.getByText('7/10 factors')).toBeInTheDocument()
  })

  it('does not render factors badge for non-F7 employer', () => {
    const emp = {
      canonical_id: 'NLRB-1', employer_name: 'NLRB Corp', city: 'DC', state: 'DC',
      unit_size: 50, source_type: 'NLRB', union_name: null,
      group_member_count: null, consolidated_workers: null,
      factors_available: null, factors_total: null,
    }
    const { container } = renderWithProviders(<SearchResultCard employer={emp} />)
    expect(container.innerHTML).not.toContain('factors')
  })

  it('renders amber warning for low factors', () => {
    const emp = {
      canonical_id: '3', employer_name: 'Low Data Inc', city: 'NY', state: 'NY',
      unit_size: 30, source_type: 'F7', union_name: null,
      group_member_count: null, consolidated_workers: null,
      factors_available: 2, factors_total: 10,
    }
    const { container } = renderWithProviders(<SearchResultCard employer={emp} />)
    expect(screen.getByText('2/10 factors')).toBeInTheDocument()
    expect(container.innerHTML).toContain('bg-amber-100')
  })

  it('renders view mode toggle in post-search state', () => {
    useEmployerSearch.mockReturnValue({
      data: {
        total: 1,
        employers: [{
          canonical_id: '1', employer_name: 'Test', city: 'NYC', state: 'NY',
          unit_size: 10, source_type: 'F7', union_name: null,
          group_member_count: null, consolidated_workers: null,
        }],
      },
      isLoading: false,
      isError: false,
    })
    renderWithProviders(<SearchPage />, '/search?q=test')
    expect(screen.getByLabelText('Table view')).toBeInTheDocument()
    expect(screen.getByLabelText('Card view')).toBeInTheDocument()
  })

  it('switches to card view when toggle clicked', () => {
    useEmployerSearch.mockReturnValue({
      data: {
        total: 1,
        employers: [{
          canonical_id: '1', employer_name: 'TestCo', city: 'NYC', state: 'NY',
          unit_size: 10, source_type: 'F7', union_name: null,
          group_member_count: null, consolidated_workers: null,
        }],
      },
      isLoading: false,
      isError: false,
    })
    renderWithProviders(<SearchPage />, '/search?q=test')
    fireEvent.click(screen.getByLabelText('Card view'))
    // Card view renders employer name inside a card layout
    expect(screen.getByText('TestCo')).toBeInTheDocument()
  })

  it('shows workers filter chip when min_workers set', () => {
    renderWithProviders(
      <SearchFilters
        filters={{ ...EMPTY_FILTERS, min_workers: '50', max_workers: '500' }}
        onSetFilter={() => {}}
        onClearFilter={() => {}}
      />
    )
    expect(screen.getByText('Workers: 50-500')).toBeInTheDocument()
  })
})
