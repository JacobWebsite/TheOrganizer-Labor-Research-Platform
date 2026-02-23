import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ResultsTable } from '@/features/search/ResultsTable'

const MOCK_DATA = [
  {
    canonical_id: 'emp-1',
    employer_name: 'Acme Corp',
    city: 'Springfield',
    state: 'IL',
    unit_size: 250,
    consolidated_workers: null,
    source_type: 'F7',
    union_name: 'SEIU Local 1',
    group_member_count: null,
  },
  {
    canonical_id: 'emp-2',
    employer_name: 'Starbucks',
    city: 'Seattle',
    state: 'WA',
    unit_size: 100,
    consolidated_workers: 5000,
    source_type: 'NLRB',
    union_name: null,
    group_member_count: 15,
  },
  {
    canonical_id: 'emp-3',
    employer_name: 'Kaiser Permanente',
    city: 'Oakland',
    state: 'CA',
    unit_size: 800,
    consolidated_workers: null,
    source_type: 'VR',
    union_name: 'UNAC/UHCP',
    group_member_count: null,
  },
]

function renderTable(props = {}) {
  return render(
    <MemoryRouter>
      <ResultsTable data={MOCK_DATA} total={75} page={1} onPageChange={() => {}} {...props} />
    </MemoryRouter>
  )
}

describe('ResultsTable', () => {
  it('renders employer rows', () => {
    renderTable()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Starbucks')).toBeInTheDocument()
    expect(screen.getByText('Kaiser Permanente')).toBeInTheDocument()
  })

  it('shows group badge for grouped employers', () => {
    renderTable()
    expect(screen.getByText('(15 locations)')).toBeInTheDocument()
  })

  it('shows source badges with correct labels', () => {
    renderTable()
    expect(screen.getByText('F7')).toBeInTheDocument()
    expect(screen.getByText('NLRB')).toBeInTheDocument()
    expect(screen.getByText('VR')).toBeInTheDocument()
  })

  it('shows pagination info', () => {
    renderTable()
    expect(screen.getByText(/Showing 1/)).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  })

  it('uses consolidated_workers when available', () => {
    renderTable()
    // Starbucks has consolidated_workers=5000
    expect(screen.getByText('5,000')).toBeInTheDocument()
  })

  it('shows union name or dash', () => {
    renderTable()
    expect(screen.getByText('SEIU Local 1')).toBeInTheDocument()
    expect(screen.getByText('UNAC/UHCP')).toBeInTheDocument()
  })

  it('disables Previous button on first page', () => {
    renderTable({ page: 1 })
    expect(screen.getByText('Previous').closest('button')).toBeDisabled()
  })

  it('disables Next button on last page', () => {
    renderTable({ page: 3, total: 75 })
    expect(screen.getByText('Next').closest('button')).toBeDisabled()
  })
})
