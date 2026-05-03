/**
 * ExecutivesCard tests (24Q-7).
 *
 * Covers:
 * - Loading / error states
 * - "No records matched" empty state
 * - Populated state: rank tally chips + executive table
 * - Show all / show top expand-collapse
 * - Vintage date footer
 * - Caveat note (rendering, not a regex check)
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ExecutivesCard } from '@/features/employer-profile/ExecutivesCard'

vi.mock('@/shared/api/profile', () => ({
  useMasterExecutives: vi.fn(),
}))

import { useMasterExecutives } from '@/shared/api/profile'

function fixturePopulated(overrides = {}) {
  return {
    summary: {
      total_executives: 12,
      with_title: 12,
      by_rank: {
        'Board Chair': 1,
        CEO: 2,
        President: 1,
        CFO: 1,
        EVP: 3,
        VP: 4,
      },
    },
    executives: [
      {
        name: 'Gregory Penner',
        title: 'Chairman of the Board',
        title_rank: 1,
        title_rank_label: 'Board Chair',
        company_name: 'Walmart Inc',
        duns: '051957769',
      },
      {
        name: 'Doug McMillon',
        title: 'Chief Executive Officer',
        title_rank: 2,
        title_rank_label: 'CEO',
        company_name: 'Walmart Inc',
        duns: '051957769',
      },
      {
        name: 'John Doe',
        title: 'President',
        title_rank: 3,
        title_rank_label: 'President',
        company_name: 'Walmart Inc',
        duns: '051957769',
      },
    ],
    source_freshness: '2026-04-27T14:51:36.620691',
    ...overrides,
  }
}

function fixtureEmpty() {
  return {
    summary: { total_executives: 0, with_title: 0, by_rank: {} },
    executives: [],
    source_freshness: null,
  }
}

describe('ExecutivesCard', () => {
  it('renders loading state', () => {
    useMasterExecutives.mockReturnValue({ data: null, isLoading: true, isError: false })
    render(<ExecutivesCard masterId={4665905} />)
    expect(screen.getByText('Executive Roster')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Executive Roster'))
    expect(screen.getByText(/Loading Mergent executive roster/)).toBeInTheDocument()
  })

  it('renders error state', () => {
    useMasterExecutives.mockReturnValue({ data: null, isLoading: false, isError: true })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    expect(screen.getByText(/Could not load Mergent/)).toBeInTheDocument()
  })

  it('renders empty state with the no-data-not-no-execs disclaimer', () => {
    useMasterExecutives.mockReturnValue({
      data: fixtureEmpty(),
      isLoading: false,
      isError: false,
    })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    expect(
      screen.getByText(/No Mergent executive records have been matched/),
    ).toBeInTheDocument()
  })

  it('renders the executive table with names and titles', () => {
    useMasterExecutives.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    // Names visible
    expect(screen.getByText('Gregory Penner')).toBeInTheDocument()
    expect(screen.getByText('Doug McMillon')).toBeInTheDocument()
    expect(screen.getByText('John Doe')).toBeInTheDocument()
    // Actual title text visible (the thing that matters most per UX feedback)
    expect(screen.getByText('Chairman of the Board')).toBeInTheDocument()
    expect(screen.getByText('Chief Executive Officer')).toBeInTheDocument()
    expect(screen.getByText('President')).toBeInTheDocument()
  })

  it('does NOT render a rank tally / hierarchy chart on the card', () => {
    // UX decision: titles matter more than rank labels. The card sorts by
    // rank but does not display rank chips, a hierarchy chart, or a
    // 'Rank' column in the table.
    useMasterExecutives.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    // Rank-label noise should not appear at all
    expect(screen.queryByText('Board Chair')).not.toBeInTheDocument()
    expect(screen.queryByText('CEO')).not.toBeInTheDocument()
    expect(screen.queryByText('EVP')).not.toBeInTheDocument()
    // Table column header 'Rank' should not be present
    expect(screen.queryByText('Rank')).not.toBeInTheDocument()
  })

  it('renders the freshness footer with vintage date', () => {
    useMasterExecutives.mockReturnValue({
      data: fixturePopulated(),
      isLoading: false,
      isError: false,
    })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    expect(screen.getByText(/Mergent data current as of/)).toBeInTheDocument()
  })

  it('shows expand button when more than VISIBLE_ROWS executives exist', () => {
    const many = Array.from({ length: 18 }, (_, i) => ({
      name: `Exec ${i + 1}`,
      title: 'Vice President',
      title_rank: 9,
      title_rank_label: 'VP',
      company_name: 'Acme Corp',
      duns: '000000001',
    }))
    useMasterExecutives.mockReturnValue({
      data: fixturePopulated({
        summary: { total_executives: 18, with_title: 18, by_rank: { VP: 18 } },
        executives: many,
      }),
      isLoading: false,
      isError: false,
    })
    render(<ExecutivesCard masterId={4665905} />)
    fireEvent.click(screen.getByText('Executive Roster'))
    // Default: 10 visible
    expect(screen.getByText('Exec 1')).toBeInTheDocument()
    expect(screen.getByText('Exec 10')).toBeInTheDocument()
    expect(screen.queryByText('Exec 11')).not.toBeInTheDocument()
    // Expand
    fireEvent.click(screen.getByText(/Show all 18 executives/))
    expect(screen.getByText('Exec 18')).toBeInTheDocument()
    // Collapse
    fireEvent.click(screen.getByText(/Show top 10 only/))
    expect(screen.queryByText('Exec 11')).not.toBeInTheDocument()
  })
})
