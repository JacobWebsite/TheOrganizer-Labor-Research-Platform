import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TargetsTable } from '@/features/scorecard/TargetsTable'

const MOCK_DATA = [
  {
    id: 101,
    display_name: 'Acme Corp',
    city: 'Springfield',
    state: 'IL',
    employee_count: 250,
    source_origin: 'sam',
    data_quality_score: 85,
    source_count: 4,
    is_federal_contractor: true,
    is_nonprofit: false,
  },
  {
    id: 102,
    display_name: 'Beta Nonprofit',
    city: 'Portland',
    state: 'OR',
    employee_count: null,
    source_origin: 'bmf',
    data_quality_score: 30,
    source_count: 1,
    is_federal_contractor: false,
    is_nonprofit: true,
  },
  {
    id: 103,
    display_name: 'Gamma Industries',
    city: 'Dallas',
    state: 'TX',
    employee_count: 5000,
    source_origin: 'mergent',
    data_quality_score: 55,
    source_count: 2,
    is_federal_contractor: false,
    is_nonprofit: false,
  },
]

function renderTable(props = {}) {
  return render(
    <MemoryRouter>
      <TargetsTable data={MOCK_DATA} total={3} page={1} pages={1} onPageChange={() => {}} {...props} />
    </MemoryRouter>
  )
}

describe('TargetsTable', () => {
  it('renders employer names', () => {
    renderTable()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Beta Nonprofit')).toBeInTheDocument()
    expect(screen.getByText('Gamma Industries')).toBeInTheDocument()
  })

  it('renders quality indicator with correct scores', () => {
    renderTable()
    expect(screen.getByText('85')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('55')).toBeInTheDocument()
  })

  it('shows forest green bar for high quality (80+)', () => {
    const { container } = renderTable()
    // Score 85 should have forest green bar
    expect(container.innerHTML).toContain('bg-[#3a7d44]')
  })

  it('shows copper bar for medium quality (50-79)', () => {
    const { container } = renderTable()
    // Score 55 should have copper bar
    expect(container.innerHTML).toContain('bg-[#c78c4e]')
  })

  it('shows stone bar for low quality (<50)', () => {
    const { container } = renderTable()
    // Score 30 should have warm stone bar
    expect(container.innerHTML).toContain('bg-[#d9cebb]')
  })

  it('formats employee count with commas', () => {
    renderTable()
    expect(screen.getByText('5,000')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
  })

  it('shows dash for null employee count', () => {
    renderTable()
    // Beta Nonprofit has null employee_count
    const cells = screen.getAllByText('\u2014')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('shows federal contractor badge', () => {
    renderTable()
    expect(screen.getByText('Fed Contractor')).toBeInTheDocument()
  })

  it('shows nonprofit badge', () => {
    renderTable()
    expect(screen.getByText('Nonprofit')).toBeInTheDocument()
  })

  it('shows signals column with -- for missing data', () => {
    renderTable()
    // Mock data has no signals_present, so all should show --
    const dashes = screen.getAllByText('--')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('shows pagination when total exceeds page size', () => {
    renderTable({ total: 100, pages: 2 })
    expect(screen.getByText('Previous')).toBeInTheDocument()
    expect(screen.getByText('Next')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
  })

  it('hides pagination when all results fit one page', () => {
    renderTable({ total: 3, pages: 1 })
    expect(screen.queryByText('Previous')).not.toBeInTheDocument()
  })
})
