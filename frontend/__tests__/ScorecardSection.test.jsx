import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScorecardSection } from '@/features/employer-profile/ScorecardSection'

const ALL_FACTORS = [
  'NLRB Activity',
  'OSHA Safety',
  'Wage & Hour',
  'Gov Contracts',
  'Union Proximity',
  'Financial',
  'Employer Size',
  'Peer Similarity',
  'Industry Growth',
]

describe('ScorecardSection', () => {
  it('returns null when scorecard is null', () => {
    const { container } = render(<ScorecardSection scorecard={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders all 9 factor labels', () => {
    const scorecard = {
      score_nlrb: 5.0,
      score_osha: 3.0,
      score_whd: 7.5,
      score_contracts: 2.0,
      score_union_proximity: 8.0,
      score_financial: 4.5,
      score_size: 6.0,
      score_similarity: 1.0,
      score_industry_growth: 9.0,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    for (const label of ALL_FACTORS) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('shows em-dash for null score values', () => {
    const scorecard = {
      score_nlrb: null,
      score_osha: null,
      score_whd: null,
      score_contracts: null,
      score_union_proximity: null,
      score_financial: null,
      score_size: null,
      score_similarity: null,
      score_industry_growth: null,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    const dashElements = screen.getAllByText('\u2014')
    expect(dashElements.length).toBe(9)
  })

  it('shows numeric value for non-null scores', () => {
    const scorecard = {
      score_nlrb: 8.2,
      score_osha: null,
      score_whd: null,
      score_contracts: null,
      score_union_proximity: null,
      score_financial: null,
      score_size: null,
      score_similarity: null,
      score_industry_growth: null,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    expect(screen.getByText('8.2')).toBeInTheDocument()
    const dashElements = screen.getAllByText('\u2014')
    expect(dashElements.length).toBe(8)
  })

  it('shows explanation text when provided', () => {
    const scorecard = { score_nlrb: 7.0 }
    const explanations = { score_nlrb: '3 elections in the last 5 years' }

    render(<ScorecardSection scorecard={scorecard} explanations={explanations} />)
    expect(screen.getByText('3 elections in the last 5 years')).toBeInTheDocument()
  })

  it('shows factor count in footer', () => {
    const scorecard = {
      score_nlrb: 5.0,
      score_osha: 3.0,
      score_whd: null,
      score_contracts: null,
      score_union_proximity: 8.0,
      score_financial: null,
      score_size: null,
      score_similarity: null,
      score_industry_growth: null,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    expect(screen.getByText(/3 of 9 factors available/)).toBeInTheDocument()
    expect(screen.getByText(/33% coverage/)).toBeInTheDocument()
  })

  it('renders colored bars for non-null values', () => {
    const scorecard = {
      score_nlrb: 8.0,  // red (>=7)
      score_osha: 5.0,  // orange (>=4)
      score_whd: 2.0,   // gray (<4)
    }

    const { container } = render(<ScorecardSection scorecard={scorecard} />)
    // Check that colored bar divs exist
    const redBars = container.querySelectorAll('.bg-red-600')
    const midBars = container.querySelectorAll('.bg-red-400')
    const lowBars = container.querySelectorAll('.bg-red-200')

    expect(redBars.length).toBeGreaterThanOrEqual(1)
    expect(midBars.length).toBeGreaterThanOrEqual(1)
    expect(lowBars.length).toBeGreaterThanOrEqual(1)
  })
})
