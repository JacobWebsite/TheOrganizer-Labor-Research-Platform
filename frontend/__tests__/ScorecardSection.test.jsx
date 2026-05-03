import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScorecardSection } from '@/features/employer-profile/ScorecardSection'

const ACTIVE_FACTORS = [
  'NLRB Activity',
  'OSHA Safety',
  'Wage & Hour',
  'Gov Contracts',
  'Union Proximity',
  'Financial',
  'Employer Size',
  'Industry Growth',
  'Peer Similarity',
]

describe('ScorecardSection', () => {
  it('returns null when scorecard is null', () => {
    const { container } = render(<ScorecardSection scorecard={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders all 9 active factor labels including Peer Similarity', () => {
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
    for (const label of ACTIVE_FACTORS) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('renders Peer Similarity factor when score is provided', () => {
    const scorecard = {
      score_similarity: 5.0,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    expect(screen.getByText('Peer Similarity')).toBeInTheDocument()
  })

  it('shows double-dash for null score values via ScoreGauge', () => {
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
    // ScoreGauge renders '--' for null values
    const dashElements = screen.getAllByText('--')
    // 9 dashes for the 9 active null factors
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
    const dashElements = screen.getAllByText('--')
    expect(dashElements.length).toBe(8)
  })

  it('shows explanation text when provided', () => {
    const scorecard = { score_nlrb: 7.0 }
    const explanations = { score_nlrb: '3 elections in the last 5 years' }

    render(<ScorecardSection scorecard={scorecard} explanations={explanations} />)
    expect(screen.getByText('3 elections in the last 5 years')).toBeInTheDocument()
  })

  it('shows factor count out of 9 active factors in footer', () => {
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
    // Total coverage counts all factors (direct + indirect)
    expect(screen.getByText(/3 of 9 factors/)).toBeInTheDocument()
    expect(screen.getByText(/33%/)).toBeInTheDocument()
    // Direct evidence counts only OSHA/NLRB/WHD/contracts/financial (2 of 5 here)
    expect(screen.getByText(/2 of 5 factors/)).toBeInTheDocument()
    expect(screen.getByText(/40%/)).toBeInTheDocument()
  })

  it('renders ScoreGauge SVG elements for non-null values', () => {
    const scorecard = {
      score_nlrb: 8.0,
      score_osha: 5.0,
      score_whd: 2.0,
    }

    const { container } = render(<ScorecardSection scorecard={scorecard} />)
    // ScoreGauge renders SVG arcs with stroke colors
    const svgs = container.querySelectorAll('svg')
    expect(svgs.length).toBeGreaterThan(0)
    // Check that score values render
    expect(screen.getByText('8.0')).toBeInTheDocument()
    expect(screen.getByText('5.0')).toBeInTheDocument()
    expect(screen.getByText('2.0')).toBeInTheDocument()
  })
})
