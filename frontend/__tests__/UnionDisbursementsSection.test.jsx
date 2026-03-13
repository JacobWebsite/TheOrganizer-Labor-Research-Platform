import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { UnionDisbursementsSection } from '@/features/union-explorer/UnionDisbursementsSection'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const MOCK_DATA = {
  file_number: '188',
  has_strike_fund: true,
  years: [
    {
      year: 2024,
      organizing: 5000000,
      compensation: 3000000,
      benefits_members: 2000000,
      administration: 1500000,
      external: 500000,
      total: 12000000,
      categories: {
        representational: 4000000,
        political: 500000,
        strike_benefits: 500000,
        to_officers: 2000000,
        to_employees: 1000000,
        benefits: 1000000,
        per_capita_tax: 200000,
        general_overhead: 500000,
        contributions: 500000,
        affiliates: 100000,
        union_administration: 400000,
        supplies: 200000,
        fees: 100000,
        administration: 200000,
        direct_taxes: 50000,
        withheld: 50000,
        members: 500000,
        investments: 100000,
        loans_made: 50000,
        loans_payment: 50000,
        other_disbursements: 0,
      },
    },
    {
      year: 2023,
      organizing: 4500000,
      compensation: 2800000,
      benefits_members: 1800000,
      administration: 1400000,
      external: 450000,
      total: 10950000,
      categories: {},
    },
  ],
}

describe('UnionDisbursementsSection', () => {
  it('renders empty state when no data', () => {
    renderWithProviders(<UnionDisbursementsSection data={null} isLoading={false} />)
    // CollapsibleCard is closed by default, click to expand
    fireEvent.click(screen.getByText('Spending Breakdown'))
    expect(screen.getByText('No disbursement data available.')).toBeInTheDocument()
  })

  it('renders spending bars and legend when expanded', () => {
    const { container } = renderWithProviders(
      <UnionDisbursementsSection data={MOCK_DATA} isLoading={false} />
    )
    // Expand card
    fireEvent.click(screen.getByText('Spending Breakdown'))
    // Check bar segments exist (colored divs)
    expect(container.innerHTML).toContain('bg-blue-500')
    expect(container.innerHTML).toContain('bg-amber-500')
    expect(container.innerHTML).toContain('bg-green-500')
    // Check legend labels (also appears in table headers, so use getAllByText)
    expect(screen.getAllByText(/Organizing/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Compensation/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders strike fund badge', () => {
    renderWithProviders(
      <UnionDisbursementsSection data={MOCK_DATA} isLoading={false} />
    )
    fireEvent.click(screen.getByText('Spending Breakdown'))
    expect(screen.getByText('Has Strike Fund')).toBeInTheDocument()
  })

  it('renders no strike fund badge', () => {
    const noStrikeData = { ...MOCK_DATA, has_strike_fund: false }
    renderWithProviders(
      <UnionDisbursementsSection data={noStrikeData} isLoading={false} />
    )
    fireEvent.click(screen.getByText('Spending Breakdown'))
    expect(screen.getByText('No Strike Fund')).toBeInTheDocument()
  })

  it('renders high officer comp badge when > 25%', () => {
    const highCompData = {
      ...MOCK_DATA,
      years: [
        {
          ...MOCK_DATA.years[0],
          compensation: 4000000,
          total: 12000000,
        },
        ...MOCK_DATA.years.slice(1),
      ],
    }
    renderWithProviders(
      <UnionDisbursementsSection data={highCompData} isLoading={false} />
    )
    fireEvent.click(screen.getByText('Spending Breakdown'))
    expect(screen.getByText(/High Officer Comp/)).toBeInTheDocument()
  })

  it('renders year-over-year table with all years', () => {
    renderWithProviders(
      <UnionDisbursementsSection data={MOCK_DATA} isLoading={false} />
    )
    fireEvent.click(screen.getByText('Spending Breakdown'))
    expect(screen.getByText('2024')).toBeInTheDocument()
    expect(screen.getByText('2023')).toBeInTheDocument()
  })

  it('returns null when loading', () => {
    const { container } = renderWithProviders(
      <UnionDisbursementsSection data={null} isLoading={true} />
    )
    expect(container.innerHTML).toBe('')
  })
})
