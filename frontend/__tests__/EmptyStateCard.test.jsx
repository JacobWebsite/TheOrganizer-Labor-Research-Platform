/**
 * EmptyStateCard convention tests (2026-05-12).
 *
 * The 2026-03-18 fix established the amber-warning empty-state pattern
 * for OSHA / NLRB / WHD / Financial / Government Contracts. The 2026-05-12
 * polish (this branch) extends the pattern to the rest of the
 * employer-profile cards via the new shared <EmptyStateCard /> component.
 *
 * These tests pin the convention down so future card additions are
 * forced to use it (i.e. cards must NOT silently return null when they
 * have no data; they must render the canonical empty panel instead).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'
import { Building2 } from 'lucide-react'

import { EmptyStateCard } from '@/shared/components/EmptyStateCard'

// Cards under test
vi.mock('@/shared/api/profile', () => ({
  useEmployerWhd: vi.fn(() => ({ data: null, isLoading: false })),
  useEmployerComparables: vi.fn(() => ({ data: { comparables: [] }, isLoading: false })),
  useEmployerCorporate: vi.fn(() => ({ data: null, isLoading: false })),
}))

import { ComparablesCard } from '@/features/employer-profile/ComparablesCard'
import { CorporateHierarchyCard } from '@/features/employer-profile/CorporateHierarchyCard'
import { DataProvenanceCard } from '@/features/employer-profile/DataProvenanceCard'
import { CrossReferencesSection } from '@/features/employer-profile/CrossReferencesSection'
import { UnionRelationshipsCard } from '@/features/employer-profile/UnionRelationshipsCard'

function renderWithProviders(ui) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('EmptyStateCard convention', () => {
  describe('shared component', () => {
    it('renders the title in the header (collapsed by default)', () => {
      render(
        <EmptyStateCard
          icon={Building2}
          title="Some Section"
          topic="thing"
        />
      )
      expect(screen.getByText('Some Section')).toBeInTheDocument()
    })

    it('renders the default summary "No records matched" when no override is given', () => {
      render(
        <EmptyStateCard
          icon={Building2}
          title="Some Section"
          topic="thing"
        />
      )
      expect(screen.getByText('No records matched')).toBeInTheDocument()
    })

    it('allows overriding the collapsed-state summary', () => {
      render(
        <EmptyStateCard
          icon={Building2}
          title="Some Section"
          topic="thing"
          summary="Custom summary"
        />
      )
      expect(screen.getByText('Custom summary')).toBeInTheDocument()
    })

    it('renders the amber panel with empty-state copy when expanded', () => {
      const { container } = render(
        <EmptyStateCard
          icon={Building2}
          title="Some Section"
          topic="thing"
        />
      )
      // Expand
      fireEvent.click(screen.getByText('Some Section'))
      // Canonical copy
      expect(screen.getByText(/No thing records have been matched/)).toBeInTheDocument()
      expect(screen.getByText(/does/)).toBeInTheDocument()
      // Amber panel marker
      const panel = container.querySelector('[data-empty-state="true"]')
      expect(panel).not.toBeNull()
      // Tailwind amber palette tokens we standardized on
      expect(panel.className).toContain('amber-300')
      expect(panel.className).toContain('amber-50')
      expect(panel.className).toContain('amber-900')
    })

    it('appends the optional reason after the canonical copy', () => {
      render(
        <EmptyStateCard
          icon={Building2}
          title="Some Section"
          topic="thing"
          reason="Coverage is limited to public companies."
        />
      )
      fireEvent.click(screen.getByText('Some Section'))
      expect(
        screen.getByText(/Coverage is limited to public companies/)
      ).toBeInTheDocument()
    })
  })

  describe('cards that previously returned null now use the convention', () => {
    it('ComparablesCard renders the empty state (not null) when no comparables', () => {
      const { container } = renderWithProviders(
        <ComparablesCard employerId="abc" />
      )
      // CRITICAL: must NOT return null — older versions silently disappeared
      expect(container.innerHTML).not.toBe('')
      expect(screen.getByText('Comparable Employers')).toBeInTheDocument()
    })

    it('CorporateHierarchyCard renders the empty state (not null) when no hierarchy', () => {
      const { container } = renderWithProviders(
        <CorporateHierarchyCard employerId="abc" />
      )
      expect(container.innerHTML).not.toBe('')
      expect(screen.getByText('Corporate Hierarchy')).toBeInTheDocument()
    })

    it('DataProvenanceCard renders the empty state (not null) when no matches', () => {
      const { container } = render(<DataProvenanceCard matchSummary={[]} />)
      expect(container.innerHTML).not.toBe('')
      expect(screen.getByText('Data Provenance')).toBeInTheDocument()
    })

    it('CrossReferencesSection renders the empty state (not null) when no refs', () => {
      const { container } = render(<CrossReferencesSection crossReferences={[]} />)
      expect(container.innerHTML).not.toBe('')
      expect(screen.getByText('Cross-References')).toBeInTheDocument()
    })

    it('UnionRelationshipsCard renders the empty state (not null) when no union', () => {
      const { container } = renderWithProviders(
        <UnionRelationshipsCard employer={{}} />
      )
      expect(container.innerHTML).not.toBe('')
      expect(screen.getByText('Union Relationships')).toBeInTheDocument()
    })
  })
})
