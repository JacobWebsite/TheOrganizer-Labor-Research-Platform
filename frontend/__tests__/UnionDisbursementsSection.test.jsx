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
  group_definitions: {
    representational: 'Contract negotiation, grievance handling, arbitration, and strike support.',
    political_lobbying: 'Political activities and lobbying expenditures.',
    staff_officers: 'Compensation and benefits for officers and staff.',
    member_benefits: 'Direct benefits paid to members.',
    operations: 'General overhead, supplies, and administrative costs.',
    affiliation_dues: 'Per capita taxes and payments to affiliates.',
    financial: 'Investments, loans, taxes, and other financial disbursements.',
  },
  years: [
    {
      year: 2024,
      representational: 4000000,
      political_lobbying: 500000,
      staff_officers: 3000000,
      member_benefits: 1000000,
      operations: 1500000,
      affiliation_dues: 300000,
      financial: 200000,
      total: 12000000,
    },
    {
      year: 2023,
      representational: 3500000,
      political_lobbying: 450000,
      staff_officers: 2800000,
      member_benefits: 900000,
      operations: 1400000,
      affiliation_dues: 280000,
      financial: 180000,
      total: 10950000,
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
    expect(screen.getAllByText(/Representational/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Staff/).length).toBeGreaterThanOrEqual(1)
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
          staff_officers: 4000000,
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
