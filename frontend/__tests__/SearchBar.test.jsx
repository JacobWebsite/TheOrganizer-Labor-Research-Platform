import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { SearchBar } from '@/features/search/SearchBar'

// Mock the employers API
vi.mock('@/shared/api/employers', () => ({
  useEmployerAutocomplete: vi.fn(() => ({ data: null })),
}))

import { useEmployerAutocomplete } from '@/shared/api/employers'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SearchBar', () => {
  beforeEach(() => {
    useEmployerAutocomplete.mockReturnValue({ data: null })
  })

  it('renders input with placeholder', () => {
    renderWithProviders(<SearchBar onSearch={() => {}} />)
    expect(screen.getByPlaceholderText('Check if an employer has a union')).toBeInTheDocument()
  })

  it('fires search on Enter', () => {
    const onSearch = vi.fn()
    renderWithProviders(<SearchBar onSearch={onSearch} />)
    const input = screen.getByPlaceholderText('Check if an employer has a union')
    fireEvent.change(input, { target: { value: 'kaiser' } })
    fireEvent.submit(input.closest('form'))
    expect(onSearch).toHaveBeenCalledWith('kaiser')
  })

  it('shows autocomplete dropdown when data is available', async () => {
    useEmployerAutocomplete.mockReturnValue({
      data: {
        employers: [
          { canonical_id: '1', employer_name: 'Kaiser Permanente', city: 'Oakland', state: 'CA' },
          { canonical_id: '2', employer_name: 'Kaiser Foundation', city: 'Pasadena', state: 'CA' },
        ],
      },
    })

    renderWithProviders(<SearchBar onSearch={() => {}} />)
    const input = screen.getByPlaceholderText('Check if an employer has a union')
    fireEvent.change(input, { target: { value: 'kai' } })
    fireEvent.focus(input)

    expect(screen.getByText('Kaiser Permanente')).toBeInTheDocument()
    expect(screen.getByText('Kaiser Foundation')).toBeInTheDocument()
  })

  it('applies hero variant styles', () => {
    renderWithProviders(<SearchBar variant="hero" onSearch={() => {}} />)
    const input = screen.getByPlaceholderText('Check if an employer has a union')
    expect(input.className).toContain('h-14')
  })

  it('applies compact variant styles', () => {
    renderWithProviders(<SearchBar variant="compact" onSearch={() => {}} />)
    const input = screen.getByPlaceholderText('Check if an employer has a union')
    expect(input.className).toContain('h-10')
  })
})
