import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { SearchFilters } from '@/features/search/SearchFilters'

// Mock lookups API
vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({
    data: {
      states: [
        { state: 'CA', employer_count: 5000, total_workers: 100000 },
        { state: 'NY', employer_count: 4000, total_workers: 80000 },
      ],
    },
  })),
  useNaicsSectors: vi.fn(() => ({
    data: {
      sectors: [
        { naics_2digit: '62', sector_name: 'Health Care' },
        { naics_2digit: '31', sector_name: 'Manufacturing' },
      ],
    },
  })),
}))

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SearchFilters', () => {
  it('renders the Filters toggle button', () => {
    renderWithProviders(
      <SearchFilters filters={{ state: '', naics: '', source_type: '' }} onSetFilter={() => {}} onClearFilter={() => {}} />
    )
    expect(screen.getByText('Filters')).toBeInTheDocument()
  })

  it('shows filter dropdowns when expanded', () => {
    renderWithProviders(
      <SearchFilters filters={{ state: '', naics: '', source_type: '' }} onSetFilter={() => {}} onClearFilter={() => {}} />
    )
    fireEvent.click(screen.getByText('Filters'))
    expect(screen.getByLabelText('Filter by state')).toBeInTheDocument()
    expect(screen.getByLabelText('Filter by industry')).toBeInTheDocument()
    expect(screen.getByLabelText('Filter by source')).toBeInTheDocument()
  })

  it('shows active filter chips', () => {
    renderWithProviders(
      <SearchFilters filters={{ state: 'CA', naics: '', source_type: '' }} onSetFilter={() => {}} onClearFilter={() => {}} />
    )
    expect(screen.getByText('State: CA')).toBeInTheDocument()
  })

  it('calls onClearFilter when chip X is clicked', () => {
    const onClear = vi.fn()
    renderWithProviders(
      <SearchFilters filters={{ state: 'CA', naics: '', source_type: '' }} onSetFilter={() => {}} onClearFilter={onClear} />
    )
    fireEvent.click(screen.getByLabelText('Remove State: CA filter'))
    expect(onClear).toHaveBeenCalledWith('state')
  })

  it('calls onSetFilter when dropdown changes', () => {
    const onSet = vi.fn()
    renderWithProviders(
      <SearchFilters filters={{ state: '', naics: '', source_type: '' }} onSetFilter={onSet} onClearFilter={() => {}} />
    )
    fireEvent.click(screen.getByText('Filters'))
    fireEvent.change(screen.getByLabelText('Filter by source'), { target: { value: 'NLRB' } })
    expect(onSet).toHaveBeenCalledWith('source_type', 'NLRB')
  })
})
