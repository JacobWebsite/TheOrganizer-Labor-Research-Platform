import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ActionLog } from '@/features/research/ActionLog'

const MOCK_ACTIONS = [
  { tool_name: 'lookup_employer', execution_order: 1, data_found: true, facts_extracted: 5, latency_ms: 120, result_summary: 'Found employer record' },
  { tool_name: 'query_osha', execution_order: 2, data_found: true, facts_extracted: 8, latency_ms: 350, result_summary: '23 violations found' },
  { tool_name: 'query_nlrb', execution_order: 3, data_found: true, facts_extracted: 3, latency_ms: 200, result_summary: '15 elections, 4 ULPs' },
  { tool_name: 'query_sec', execution_order: 4, data_found: false, facts_extracted: 0, latency_ms: 150, result_summary: 'No SEC filings matched' },
  { tool_name: 'query_990', execution_order: 5, data_found: false, facts_extracted: 0, latency_ms: 80, result_summary: 'No 990 filings' },
  { tool_name: 'query_whd', execution_order: 6, data_found: false, facts_extracted: 0, latency_ms: 90, error_message: 'WHD API timeout' },
]

function expandCard() {
  // CollapsibleCard defaults closed -- click header to open
  const header = document.querySelector('[data-slot="card-header"]') || screen.getByText('Action Log').closest('[class*="cursor-pointer"]')
  fireEvent.click(header)
}

describe('ActionLog', () => {
  it('returns null for empty actions', () => {
    const { container } = render(<ActionLog actions={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows category breakdown in collapsed summary', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expect(screen.getByText(/6 tools called/)).toBeInTheDocument()
    expect(screen.getByText(/3 found data/)).toBeInTheDocument()
    expect(screen.getByText(/1 error/)).toBeInTheDocument()
  })

  it('shows summary bar with correct counts when expanded', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    expect(screen.getByText('3/6 tools found data')).toBeInTheDocument()
    expect(screen.getByText('1 error')).toBeInTheDocument()
    expect(screen.getByText('1.0s total')).toBeInTheDocument()
  })

  it('shows found-data tools in main table', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    expect(screen.getByText('lookup_employer')).toBeInTheDocument()
    expect(screen.getByText('query_osha')).toBeInTheDocument()
    expect(screen.getByText('query_nlrb')).toBeInTheDocument()
  })

  it('shows errored tools with error message', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    expect(screen.getByText('query_whd')).toBeInTheDocument()
    expect(screen.getByText('WHD API timeout')).toBeInTheDocument()
  })

  it('shows error text with destructive styling', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    const errorCell = screen.getByText('WHD API timeout')
    expect(errorCell.className).toContain('text-destructive')
  })

  it('collapses not-found tools by default', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    expect(screen.getByText(/2 tools returned no data/)).toBeInTheDocument()
    // Tool names shown in parenthetical preview
    expect(screen.getByText(/query_sec, query_990/)).toBeInTheDocument()
  })

  it('expands not-found tools on click', () => {
    render(<ActionLog actions={MOCK_ACTIONS} />)
    expandCard()
    const notFoundBtn = screen.getByText(/2 tools returned no data/)
    fireEvent.click(notFoundBtn)
    // After expanding, individual tool entries appear as separate elements
    const allSecTexts = screen.getAllByText('query_sec')
    expect(allSecTexts.length).toBeGreaterThanOrEqual(1)
    const all990Texts = screen.getAllByText('query_990')
    expect(all990Texts.length).toBeGreaterThanOrEqual(1)
  })

  it('handles all-found actions (no error/not-found sections)', () => {
    const allFound = MOCK_ACTIONS.filter(a => a.data_found && !a.error_message)
    render(<ActionLog actions={allFound} />)
    expandCard()
    expect(screen.getByText('3/3 tools found data')).toBeInTheDocument()
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/returned no data/)).not.toBeInTheDocument()
  })
})
