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
]

describe('ScorecardSection', () => {
  it('returns null when scorecard is null', () => {
    const { container } = render(<ScorecardSection scorecard={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders all 8 active factor labels plus disabled Peer Similarity', () => {
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
    // Peer Similarity is still rendered but as disabled
    expect(screen.getByText('Peer Similarity')).toBeInTheDocument()
  })

  it('shows "Under Development" for disabled score_similarity', () => {
    const scorecard = {
      score_similarity: 5.0,
    }

    render(<ScorecardSection scorecard={scorecard} />)
    expect(screen.getByText('Under Development')).toBeInTheDocument()
  })

  it('shows em-dash for null score values on active factors', () => {
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
    // 8 dashes for the 8 active null factors (similarity shows "Under Development" instead)
    expect(dashElements.length).toBe(8)
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
    expect(dashElements.length).toBe(7)
  })

  it('shows explanation text when provided', () => {
    const scorecard = { score_nlrb: 7.0 }
    const explanations = { score_nlrb: '3 elections in the last 5 years' }

    render(<ScorecardSection scorecard={scorecard} explanations={explanations} />)
    expect(screen.getByText('3 elections in the last 5 years')).toBeInTheDocument()
  })

  it('shows factor count out of 8 active factors in footer', () => {
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
    expect(screen.getByText(/3 of 8 factors available/)).toBeInTheDocument()
    expect(screen.getByText(/38% coverage/)).toBeInTheDocument()
  })

  it('renders colored bars for non-null values', () => {
    const scorecard = {
      score_nlrb: 8.0,  // brick red (>=7)
      score_osha: 5.0,  // copper (>=4)
      score_whd: 2.0,   // stone (<4)
    }

    const { container } = render(<ScorecardSection scorecard={scorecard} />)
    const html = container.innerHTML
    // Check that colored bar classes exist (aged broadsheet palette)
    expect(html).toContain('bg-[#c23a22]')  // high signal (brick red)
    expect(html).toContain('bg-[#c78c4e]')  // mid signal (copper)
    expect(html).toContain('bg-[#d9cebb]')  // low signal (warm stone)
  })
})
