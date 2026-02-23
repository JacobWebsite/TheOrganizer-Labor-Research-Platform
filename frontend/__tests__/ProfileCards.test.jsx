import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

// Mock ALL profile hooks used by cards
vi.mock('@/shared/api/profile', () => ({
  useEmployerWhd: vi.fn(() => ({ data: null, isLoading: false })),
  useEmployerComparables: vi.fn(() => ({ data: null, isLoading: false })),
  useEmployerCorporate: vi.fn(() => ({ data: null, isLoading: false })),
  useEmployerFlags: vi.fn(() => ({ data: { flags: [] }, isLoading: false })),
  useFlagEmployer: vi.fn(() => ({ mutate: vi.fn(), isPending: false, isError: false })),
  useEmployerDataSources: vi.fn(() => ({ data: null, isLoading: false })),
  parseCanonicalId: vi.fn((id) => ({ isF7: true, sourceType: 'F7', rawId: id })),
  useEmployerProfile: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useEmployerUnifiedDetail: vi.fn(() => ({ data: null, isLoading: false, isError: false })),
  useScorecardDetail: vi.fn(() => ({ data: null, isLoading: false })),
}))

import { useEmployerWhd, useEmployerComparables, useEmployerCorporate, useEmployerFlags } from '@/shared/api/profile'

// Import all card components
import { UnionRelationshipsCard } from '@/features/employer-profile/UnionRelationshipsCard'
import { FinancialDataCard } from '@/features/employer-profile/FinancialDataCard'
import { GovernmentContractsCard } from '@/features/employer-profile/GovernmentContractsCard'
import { WhdCard } from '@/features/employer-profile/WhdCard'
import { ComparablesCard } from '@/features/employer-profile/ComparablesCard'
import { CorporateHierarchyCard } from '@/features/employer-profile/CorporateHierarchyCard'
import { ResearchNotesCard } from '@/features/employer-profile/ResearchNotesCard'
import { ProfileActionButtons } from '@/features/employer-profile/ProfileActionButtons'
import { ProfileHeader } from '@/features/employer-profile/ProfileHeader'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ProfileCards', () => {
  beforeEach(() => {
    useEmployerWhd.mockReturnValue({ data: null, isLoading: false })
    useEmployerComparables.mockReturnValue({ data: null, isLoading: false })
    useEmployerCorporate.mockReturnValue({ data: null, isLoading: false })
    useEmployerFlags.mockReturnValue({ data: { flags: [] }, isLoading: false })
  })

  // -- UnionRelationshipsCard --
  it('UnionRelationshipsCard shows union name when expanded', () => {
    const employer = { latest_union_name: 'SEIU Local 32BJ', latest_union_fnum: '123456', latest_unit_size: 500 }
    renderWithProviders(<UnionRelationshipsCard employer={employer} />)
    // CollapsibleCard shows summary when collapsed, content when expanded
    expect(screen.getByText('Union Relationships')).toBeInTheDocument()
    // Click to expand
    fireEvent.click(screen.getByText('Union Relationships'))
    expect(screen.getByText('SEIU Local 32BJ')).toBeInTheDocument()
  })

  it('UnionRelationshipsCard returns null with no union', () => {
    const { container } = renderWithProviders(<UnionRelationshipsCard employer={{}} />)
    expect(container.innerHTML).toBe('')
  })

  // -- FinancialDataCard --
  it('FinancialDataCard shows growth percentage', () => {
    const scorecard = { bls_growth_pct: 3.5, score_financial: 6.0 }
    renderWithProviders(<FinancialDataCard scorecard={scorecard} dataSources={{}} />)
    fireEvent.click(screen.getByText('Financial Data'))
    expect(screen.getByText('3.5%')).toBeInTheDocument()
  })

  it('FinancialDataCard shows public company info', () => {
    renderWithProviders(<FinancialDataCard scorecard={{}} dataSources={{ is_public: true, ticker: 'AAPL' }} />)
    fireEvent.click(screen.getByText('Financial Data'))
    expect(screen.getByText('Yes (AAPL)')).toBeInTheDocument()
  })

  // -- GovernmentContractsCard --
  it('GovernmentContractsCard shows obligations', () => {
    renderWithProviders(
      <GovernmentContractsCard dataSources={{ is_federal_contractor: true, federal_obligations: 1000000, federal_contract_count: 5 }} />
    )
    fireEvent.click(screen.getByText('Government Contracts'))
    expect(screen.getByText('$1,000,000')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('GovernmentContractsCard returns null when not contractor', () => {
    const { container } = renderWithProviders(<GovernmentContractsCard dataSources={{ is_federal_contractor: false }} />)
    expect(container.innerHTML).toBe('')
  })

  // -- WhdCard --
  it('WhdCard shows cases table', () => {
    useEmployerWhd.mockReturnValue({
      data: {
        whd_summary: { case_count: 3, total_violations: 10, total_backwages: 50000, total_penalties: 10000 },
        cases: [
          { trade_name: 'Acme Foods', city: 'NYC', state: 'NY', violations_count: 5, backwages: 25000 },
        ],
      },
      isLoading: false,
    })
    renderWithProviders(<WhdCard employerId="abc123" />)
    fireEvent.click(screen.getByText('Wage & Hour (WHD)'))
    expect(screen.getByText('Acme Foods')).toBeInTheDocument()
  })

  // -- ComparablesCard --
  it('ComparablesCard shows comparable employers', () => {
    useEmployerComparables.mockReturnValue({
      data: {
        comparables: [
          { rank: 1, comparable_name: 'Similar Corp', comparable_id: 100, similarity_pct: 85, match_reasons: ['Same industry'], union_name: 'UAW' },
        ],
      },
      isLoading: false,
    })
    renderWithProviders(<ComparablesCard employerId="abc123" />)
    fireEvent.click(screen.getByText('Comparable Employers'))
    expect(screen.getByText('Similar Corp')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  // -- CorporateHierarchyCard --
  it('CorporateHierarchyCard shows parent', () => {
    useEmployerCorporate.mockReturnValue({
      data: {
        ultimate_parent: { name: 'MegaCorp Inc', ticker: 'MEGA' },
        parent_chain: [{ name: 'SubDiv LLC' }],
        subsidiaries: [],
        family_union_status: { total_family: 5, unionized_count: 2 },
      },
      isLoading: false,
    })
    renderWithProviders(<CorporateHierarchyCard employerId="abc123" />)
    fireEvent.click(screen.getByText('Corporate Hierarchy'))
    expect(screen.getByText('MegaCorp Inc')).toBeInTheDocument()
  })

  // -- ResearchNotesCard --
  it('ResearchNotesCard shows existing flags', () => {
    useEmployerFlags.mockReturnValue({
      data: {
        flags: [
          { id: 1, flag_type: 'DATA_QUALITY', notes: 'Wrong address', created_at: '2026-02-20T00:00:00' },
        ],
      },
      isLoading: false,
    })
    renderWithProviders(<ResearchNotesCard employerId="abc123" sourceType="F7" sourceId="abc123" />)
    fireEvent.click(screen.getByText('Research Notes'))
    expect(screen.getByText('Wrong address')).toBeInTheDocument()
  })

  it('ResearchNotesCard shows add form on click', () => {
    useEmployerFlags.mockReturnValue({ data: { flags: [] }, isLoading: false })
    renderWithProviders(<ResearchNotesCard employerId="abc123" sourceType="F7" sourceId="abc123" />)
    fireEvent.click(screen.getByText('Research Notes'))
    fireEvent.click(screen.getByText('Add Note'))
    expect(screen.getByLabelText('Note type')).toBeInTheDocument()
  })

  // -- ProfileActionButtons --
  it('ProfileActionButtons renders all three buttons', () => {
    renderWithProviders(<ProfileActionButtons employer={{ employer_id: 'abc123' }} scorecard={{}} />)
    expect(screen.getByText('Flag as Target')).toBeInTheDocument()
    expect(screen.getByText('Export Data')).toBeInTheDocument()
    expect(screen.getByText('Something Looks Wrong')).toBeInTheDocument()
  })

  // -- ProfileHeader union status --
  it('ProfileHeader shows Represented by label', () => {
    const employer = { employer_name: 'Test Corp', union_name: 'SEIU Local 1' }
    renderWithProviders(<ProfileHeader employer={employer} scorecard={{}} sourceType="F7" />)
    expect(screen.getByText(/Represented by SEIU Local 1/)).toBeInTheDocument()
  })

  it('ProfileHeader shows No Known Union', () => {
    const employer = { employer_name: 'Test Corp' }
    renderWithProviders(<ProfileHeader employer={employer} scorecard={{}} sourceType="F7" />)
    expect(screen.getByText('No Known Union')).toBeInTheDocument()
  })
})
