import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { SearchPage } from '@/features/search/SearchPage'

// Mock the API hooks
vi.mock('@/shared/api/employers', () => ({
  useEmployerSearch: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useEmployerAutocomplete: vi.fn(() => ({ data: null })),
}))

vi.mock('@/shared/api/lookups', () => ({
  useStates: vi.fn(() => ({ data: { states: [] } })),
  useNaicsSectors: vi.fn(() => ({ data: { sectors: [] } })),
}))

import { useEmployerSearch } from '@/shared/api/employers'

function renderWithRoute(initialEntry = '/search') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <SearchPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SearchPage', () => {
  beforeEach(() => {
    useEmployerSearch.mockReturnValue({ data: null, isLoading: false, isError: false })
  })

  it('shows hero search bar in pre-search state', () => {
    renderWithRoute('/search')
    expect(screen.getByText('Union Employer Search')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Check if an employer has a union')).toBeInTheDocument()
    // Hero variant uses h-14
    const input = screen.getByPlaceholderText('Check if an employer has a union')
    expect(input.className).toContain('h-14')
  })

  it('shows results table in post-search state', () => {
    useEmployerSearch.mockReturnValue({
      data: {
        total: 2,
        employers: [
          { canonical_id: '1', employer_name: 'Acme Corp', city: 'NYC', state: 'NY', unit_size: 100, source_type: 'F7', union_name: null, group_member_count: null, consolidated_workers: null },
          { canonical_id: '2', employer_name: 'Beta Inc', city: 'LA', state: 'CA', unit_size: 50, source_type: 'NLRB', union_name: 'SEIU', group_member_count: null, consolidated_workers: null },
        ],
      },
      isLoading: false,
      isError: false,
    })

    renderWithRoute('/search?q=acme')
    // Result header has count in <strong> tag, search with function matcher
    expect(screen.getByText((_, el) => el?.getAttribute?.('aria-live') === 'polite')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Beta Inc')).toBeInTheDocument()
  })

  it('shows empty state when no results', () => {
    useEmployerSearch.mockReturnValue({
      data: { total: 0, employers: [] },
      isLoading: false,
      isError: false,
    })

    renderWithRoute('/search?q=zzzzzzz')
    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('shows loading skeleton', () => {
    useEmployerSearch.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    })

    renderWithRoute('/search?q=test')
    // PageSkeleton renders animated pulse divs
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows error message on API failure', () => {
    useEmployerSearch.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { message: 'Server error' },
    })

    renderWithRoute('/search?q=test')
    expect(screen.getByText(/Server error/)).toBeInTheDocument()
  })
})
