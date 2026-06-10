/**
 * CustomersCard tests (24Q-19).
 *
 * Smoke tests for the Customers thin wrapper. The shared
 * RelationshipBody behavior is exercised more thoroughly in
 * SuppliersCard.test.jsx; here we just confirm the wrapper passes the
 * right empty copy + title + hook through.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CustomersCard } from '@/features/employer-profile/CustomersCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterCustomers: vi.fn(),
  useMasterSuppliers: vi.fn(),
  useMasterDistributionPartners: vi.fn(),
}))

import { useMasterCustomers } from '@/shared/api/profile'

describe('CustomersCard', () => {
  it('renders loading state with the Customers title', () => {
    useMasterCustomers.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<CustomersCard masterId={12345} />)
    expect(screen.getByText('Customers')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Customers'))
    expect(screen.getByText(/Loading 10-K relationships/)).toBeInTheDocument()
  })

  it('renders empty state with the customer-specific copy', () => {
    useMasterCustomers.mockReturnValue({
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
    render(<CustomersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Customers'))
    expect(
      screen.getByText('No customer mentions found in recent 10-K filings.'),
    ).toBeInTheDocument()
  })

  it('renders populated rows with name + linked profile', () => {
    useMasterCustomers.mockReturnValue({
      data: {
        master_id: 12345,
        items: [
          {
            child_master_id: 99,
            name: 'BIG BUYER CO',
            confidence: 0.96,
            match_method: 'exact',
            source_filing: { cik: '1', accession_number: 'a', filing_date: '2024-12-01' },
            context: 'represents 12% of total revenue',
          },
          {
            child_master_id: null,
            name: 'SMALL BUYER',
            confidence: 0.6,
            match_method: 'trigram',
            source_filing: null,
            context: null,
          },
        ],
        total_extracted: 2,
        total_matched: 1,
        stale: false,
      },
      isLoading: false,
      isError: false,
    })
    render(<CustomersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Customers'))
    expect(screen.getByText('BIG BUYER CO')).toBeInTheDocument()
    expect(screen.getByText('SMALL BUYER')).toBeInTheDocument()
    // Linked
    expect(screen.getByText('BIG BUYER CO').closest('a')).toHaveAttribute(
      'href', '/employers/MASTER-99',
    )
    // Unmatched plain text
    expect(screen.getByText('SMALL BUYER').closest('a')).toBeNull()
  })

  it('renders the stale warning banner', () => {
    useMasterCustomers.mockReturnValue({
      data: {
        master_id: 12345,
        items: [
          {
            child_master_id: 1,
            name: 'X',
            confidence: 0.9,
            match_method: 'trigram',
            source_filing: null,
            context: null,
          },
        ],
        total_extracted: 1,
        total_matched: 1,
        stale: true,
      },
      isLoading: false,
      isError: false,
    })
    const { container } = render(<CustomersCard masterId={12345} />)
    fireEvent.click(screen.getByText('Customers'))
    expect(container.querySelector('[data-testid="stale-warning"]')).toBeTruthy()
  })
})
