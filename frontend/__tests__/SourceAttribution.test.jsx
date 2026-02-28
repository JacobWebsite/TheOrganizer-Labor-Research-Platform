import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SourceAttribution } from '@/shared/components/SourceAttribution'

const mockAttribution = {
  source_system: 'osha',
  source_label: 'OSHA Establishment Records',
  citation: 'OSHA Establishment Records matched by EIN (exact match)',
  best_confidence_score: 1.0,
  best_match_tier: 'EIN_EXACT',
}

describe('SourceAttribution', () => {
  it('renders nothing when attribution is null', () => {
    const { container } = render(<SourceAttribution attribution={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when attribution is undefined', () => {
    const { container } = render(<SourceAttribution />)
    expect(container.innerHTML).toBe('')
  })

  it('renders source badge and citation when provided', () => {
    render(<SourceAttribution attribution={mockAttribution} />)
    expect(screen.getByText('osha')).toBeInTheDocument()
    expect(screen.getByText('OSHA Establishment Records matched by EIN (exact match)')).toBeInTheDocument()
  })

  it('falls back to source_label when citation is missing', () => {
    const attr = { ...mockAttribution, citation: null }
    render(<SourceAttribution attribution={attr} />)
    expect(screen.getByText('OSHA Establishment Records')).toBeInTheDocument()
  })

  it('renders confidence dots', () => {
    const { container } = render(<SourceAttribution attribution={mockAttribution} />)
    // ConfidenceDots renders 4 span elements for dots
    const dots = container.querySelectorAll('.rounded-full')
    expect(dots.length).toBe(4)
  })

  it('applies source-specific color class for osha', () => {
    const { container } = render(<SourceAttribution attribution={mockAttribution} />)
    const badge = container.querySelector('.bg-amber-100')
    expect(badge).toBeTruthy()
  })

  it('applies source-specific color class for nlrb', () => {
    const nlrbAttr = { ...mockAttribution, source_system: 'nlrb' }
    const { container } = render(<SourceAttribution attribution={nlrbAttr} />)
    const badge = container.querySelector('.bg-blue-100')
    expect(badge).toBeTruthy()
  })

  it('applies fallback color for unknown source', () => {
    const unknownAttr = { ...mockAttribution, source_system: 'unknown_src' }
    const { container } = render(<SourceAttribution attribution={unknownAttr} />)
    const badge = container.querySelector('.bg-muted')
    expect(badge).toBeTruthy()
  })
})
