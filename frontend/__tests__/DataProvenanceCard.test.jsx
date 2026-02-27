import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DataProvenanceCard } from '@/features/employer-profile/DataProvenanceCard'

const mockSummary = [
  {
    source_system: 'osha',
    source_label: 'OSHA Establishment Records',
    match_count: 3,
    best_confidence_score: 1.0,
    best_method: 'EIN_EXACT',
    best_confidence_band: 'HIGH',
    best_match_tier: 'EIN_EXACT',
    citation: 'OSHA Establishment Records matched by EIN (exact match)',
  },
  {
    source_system: 'nlrb',
    source_label: 'NLRB Case Records',
    match_count: 1,
    best_confidence_score: 0.87,
    best_method: 'FUZZY_SPLINK_ADAPTIVE',
    best_confidence_band: 'MEDIUM',
    best_match_tier: 'FUZZY_SPLINK_ADAPTIVE',
    citation: 'NLRB Case Records matched by fuzzy name matching (0.87 similarity)',
  },
]

describe('DataProvenanceCard', () => {
  it('renders null when no data', () => {
    const { container } = render(<DataProvenanceCard matchSummary={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders null when empty array', () => {
    const { container } = render(<DataProvenanceCard matchSummary={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows title and summary when collapsed', () => {
    render(<DataProvenanceCard matchSummary={mockSummary} />)
    expect(screen.getByText('Data Provenance')).toBeInTheDocument()
    expect(screen.getByText('2 sources linked')).toBeInTheDocument()
  })

  it('shows source badges and citations when expanded', () => {
    render(<DataProvenanceCard matchSummary={mockSummary} />)
    // Click header to expand
    fireEvent.click(screen.getByText('Data Provenance'))
    expect(screen.getByText('osha')).toBeInTheDocument()
    expect(screen.getByText('nlrb')).toBeInTheDocument()
    expect(screen.getByText('OSHA Establishment Records')).toBeInTheDocument()
    expect(screen.getByText('NLRB Case Records')).toBeInTheDocument()
    expect(screen.getByText('OSHA Establishment Records matched by EIN (exact match)')).toBeInTheDocument()
  })

  it('shows match count for multi-record sources when expanded', () => {
    render(<DataProvenanceCard matchSummary={mockSummary} />)
    fireEvent.click(screen.getByText('Data Provenance'))
    expect(screen.getByText('3 records')).toBeInTheDocument()
    // Single-record source should not show count
    expect(screen.queryByText('1 records')).not.toBeInTheDocument()
  })
})
