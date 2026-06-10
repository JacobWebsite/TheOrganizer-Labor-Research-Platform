/**
 * SuppliersCard tests (24Q-16).
 *
 * Covers the shared RelationshipBody contract through the Suppliers
 * thin wrapper:
 *  - loading state shows skeleton
 *  - empty state renders empty copy
 *  - populated state renders names, confidence chips, linked + unmatched rows
 *  - stale flag renders the warning banner
 *  - confidence-chip color tiers (GREEN >= 0.95, YELLOW 0.85-0.95, GRAY < 0.85 / unmatched)
 *  - unmatched row renders as plain text with no anchor
 *
 * Pattern mirrors LobbyingCard.test.jsx and CompetitorsCard.test.jsx:
 * mock the hook, click the CollapsibleCard title to expand, assert.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SuppliersCard } from '@/features/employer-profile/SuppliersCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterSuppliers: vi.fn(),
  useMasterCustomers: vi.fn(),
  useMasterDistributionPartners: vi.fn(),
}))

import { useMasterSuppliers } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    master_id: 12345,
    relationship_type: 'supplier',
    source: '10-K text mining',
    as_of: '2026-04-01',
    items: [
      {
        child_master_id: 7087569,
        name: 'PFIZER, INC.',
        confidence: 0.99,
        match_method: 'exact',
        source_filing: { cik: '0000078003', accession_number: 'a1', filing_date: '2025-02-21' },
        context: 'major raw-material supplier referenced in Item 1',
      },
      {
        child_master_id: 4036186,
        name: 'JOHNSON CONTROLS',
        confidence: 0.9,
        match_method: 'trigram',
        source_filing: { cik: '0000078003', accession_number: 'a1', filing_date: '2025-02-21' },
        context: 'building automation systems',
      },
      {
        child_master_id: null,
        name: 'BLUE STAR PACKAGING (unmatched)',
        confidence: 0.8,
        match_method: 'unmatched',
        source_filing: { cik: '0000078003', accession_number: 'a1', filing_date: '2025-02-21' },
        context: null,
      },
    ],
    total_extracted: 5,
    total_matched: 2,
    stale: false,
    ...overrides,
  }
}

describe('SuppliersCard', () => {
  it('renders loading state with skeleton rows', () => {
    useMasterSuppliers.mockReturnValue({ data: null, isLoading: true, isError: false })
    const { container } = render(<SuppliersCard masterId={12345} />)
    expect(screen.getByText('Suppliers')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Suppliers'))
    expect(screen.getByText(/Loading 10-K relationships/)).toBeInTheDocument()
    expect(container.querySelector('[data-testid="relationship-skeleton"]')).toBeTruthy()
  })

  it('renders error state with retry button', () => {
    const refetch = vi.fn()
    useMasterSuppliers.mockReturnValue({
      data: null, isLoading: false, isError: true, refetch,
    })
    render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    expect(screen.getByText(/Could not load 10-K relationships/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('renders empty state when items is empty', () => {
    useMasterSuppliers.mockReturnValue({
      data: {
        master_id: 12345,
        items: [],
        total_extracted: 0,
        total_matched: 0,
        stale: false,
        as_of: '2026-04-01',
      },
      isLoading: false,
      isError: false,
    })
    render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    expect(
      screen.getByText('No supplier mentions found in recent 10-K filings.'),
    ).toBeInTheDocument()
    // Footer source attribution always renders
    expect(screen.getByText(/Source: 10-K text mining/)).toBeInTheDocument()
  })

  it('renders populated rows with linked names and confidence chips', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    expect(screen.getByText('PFIZER, INC.')).toBeInTheDocument()
    expect(screen.getByText('JOHNSON CONTROLS')).toBeInTheDocument()
    // Linked rows wrap the name in an anchor pointing at the master profile
    const pfizerLink = screen.getByText('PFIZER, INC.').closest('a')
    expect(pfizerLink).toHaveAttribute('href', '/employers/MASTER-7087569')
    const jcLink = screen.getByText('JOHNSON CONTROLS').closest('a')
    expect(jcLink).toHaveAttribute('href', '/employers/MASTER-4036186')
    // Confidence chip text renders alongside each row -- 99% / 90%
    expect(screen.getByText('99%')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    // Footer summary mentions the source + filing date (Feb 21, 2025 stringified by toLocaleDateString)
    expect(screen.getByText(/Source: 10-K text mining/)).toBeInTheDocument()
    expect(screen.getByText(/latest filing/)).toBeInTheDocument()
  })

  it('renders unmatched row as plain text (no anchor)', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated(), isLoading: false, isError: false,
    })
    render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    const unmatchedNode = screen.getByText('BLUE STAR PACKAGING (unmatched)')
    expect(unmatchedNode).toBeInTheDocument()
    // No <a> wrapper around an unmatched row.
    expect(unmatchedNode.closest('a')).toBeNull()
    // Footer reports the unmatched count: total_extracted (5) - total_matched (2) = 3.
    expect(screen.getByText(/3 unmatched/)).toBeInTheDocument()
  })

  it('renders stale warning banner when stale=true', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated({ stale: true }), isLoading: false, isError: false,
    })
    const { container } = render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    expect(container.querySelector('[data-testid="stale-warning"]')).toBeTruthy()
    expect(
      screen.getByText(/Stale: most recent 10-K is more than two years old/),
    ).toBeInTheDocument()
  })

  it('confidence chip uses GREEN for >= 0.95', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated({
        items: [
          {
            child_master_id: 1,
            name: 'GREEN CO',
            confidence: 0.97,
            match_method: 'exact',
            source_filing: null,
            context: null,
          },
        ],
      }),
      isLoading: false,
      isError: false,
    })
    const { container } = render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    // Hex #3a7d44 = forest green. Tailwind arbitrary-value classes can't be
    // selected with querySelector reliably (jsdom escaping), so probe innerHTML.
    expect(container.innerHTML.includes('bg-[#3a7d44]')).toBe(true)
    expect(container.innerHTML.includes('bg-[#c78c4e]')).toBe(false)
  })

  it('confidence chip uses YELLOW for 0.85-0.95', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated({
        items: [
          {
            child_master_id: 1,
            name: 'YELLOW CO',
            confidence: 0.9,
            match_method: 'trigram',
            source_filing: null,
            context: null,
          },
        ],
      }),
      isLoading: false,
      isError: false,
    })
    const { container } = render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    // Hex #c78c4e = copper.
    expect(container.innerHTML.includes('bg-[#c78c4e]')).toBe(true)
    expect(container.innerHTML.includes('bg-[#3a7d44]')).toBe(false)
  })

  it('confidence chip uses GRAY for < 0.85 and for unmatched', () => {
    useMasterSuppliers.mockReturnValue({
      data: fixturePopulated({
        items: [
          {
            child_master_id: 1,
            name: 'LOWCONF CO',
            confidence: 0.5,
            match_method: 'trigram',
            source_filing: null,
            context: null,
          },
          {
            child_master_id: null,
            name: 'NOMATCH CO',
            confidence: null,
            match_method: 'unmatched',
            source_filing: null,
            context: null,
          },
        ],
      }),
      isLoading: false,
      isError: false,
    })
    const { container } = render(<SuppliersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Suppliers'))
    // Hex #d9cebb = warm stone (gray).
    expect(container.innerHTML.includes('bg-[#d9cebb]')).toBe(true)
    expect(screen.getByText('unmatched')).toBeInTheDocument()
  })
})
