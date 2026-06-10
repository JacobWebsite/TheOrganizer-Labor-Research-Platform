/**
 * DistributionCard tests (24Q-17).
 *
 * Smoke tests for the Distribution thin wrapper. The shared
 * RelationshipBody behavior is exercised more thoroughly in
 * SuppliersCard.test.jsx; here we just confirm the wrapper passes the
 * right empty copy + title + hook through.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DistributionCard } from '@/features/employer-profile/DistributionCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterDistributionPartners: vi.fn(),
  useMasterSuppliers: vi.fn(),
  useMasterCustomers: vi.fn(),
}))

import { useMasterDistributionPartners } from '@/shared/api/profile'

describe('DistributionCard', () => {
  it('renders the Distribution Partners title in loading state', () => {
    useMasterDistributionPartners.mockReturnValue({
      data: null, isLoading: true, isError: false,
    })
    render(<DistributionCard masterId={12345} />)
    expect(screen.getByText('Distribution Partners')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Distribution Partners'))
    expect(screen.getByText(/Loading 10-K relationships/)).toBeInTheDocument()
  })

  it('renders empty state with the distribution-specific copy', () => {
    useMasterDistributionPartners.mockReturnValue({
      data: {
        master_id: 12345,
        items: [],
        total_extracted: 0,
        total_matched: 0,
        stale: false,
      },
      isLoading: false,
      isError: false,
    })
    render(<DistributionCard masterId={12345} />)
    fireEvent.click(screen.getByText('Distribution Partners'))
    expect(
      screen.getByText(
        'No distribution-partner mentions found in recent 10-K filings.',
      ),
    ).toBeInTheDocument()
  })

  it('renders one populated row with confidence chip', () => {
    useMasterDistributionPartners.mockReturnValue({
      data: {
        master_id: 12345,
        items: [
          {
            child_master_id: 7,
            name: 'TRANSPORT BRO LLC',
            confidence: 0.92,
            match_method: 'trigram',
            source_filing: { cik: '1', accession_number: 'a', filing_date: '2025-03-15' },
            context: 'primary nationwide distributor',
          },
        ],
        total_extracted: 1,
        total_matched: 1,
        stale: false,
      },
      isLoading: false,
      isError: false,
    })
    render(<DistributionCard masterId={12345} />)
    fireEvent.click(screen.getByText('Distribution Partners'))
    expect(screen.getByText('TRANSPORT BRO LLC')).toBeInTheDocument()
    expect(screen.getByText('TRANSPORT BRO LLC').closest('a')).toHaveAttribute(
      'href', '/employers/MASTER-7',
    )
    // 0.92 -> YELLOW chip with "92%"
    expect(screen.getByText('92%')).toBeInTheDocument()
  })
})
