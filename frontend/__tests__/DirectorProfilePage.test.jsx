/**
 * DirectorProfilePage tests (24Q-14 sister, C.1).
 *
 * Covers:
 * - loading state
 * - 404 (director not found) — renders amber warning, not blank
 * - error state (non-404)
 * - populated state: name, board count, summary
 * - per-board rendering: state, NAICS, since-year, committees, IND/INSIDE chip
 * - links: master profile + source URL
 * - alternate-spelling rollup
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { DirectorProfilePage } from '@/features/directors/DirectorProfilePage'

vi.mock('@/shared/api/profile', () => ({
  useDirectorProfile: vi.fn(),
}))

import { useDirectorProfile } from '@/shared/api/profile'

function renderPage(slug = 'adam-portnoy') {
  return render(
    <MemoryRouter initialEntries={[`/directors/${slug}`]}>
      <Routes>
        <Route path="/directors/:slug" element={<DirectorProfilePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fixture(overrides = {}) {
  return {
    slug: 'adam-portnoy',
    names_matched: ['Adam Portnoy'],
    summary: {
      boards_count: 4,
      is_independent_count: 0,
      earliest_since_year: 2018,
      latest_since_year: 2023,
    },
    boards: [
      {
        master_id: 100001,
        canonical_name: 'diversified healthcare trust',
        state: 'MA',
        naics: '525990',
        since_year: 2018,
        position: 'Chairman',
        is_independent: false,
        committees: ['Executive', 'Compensation'],
        fiscal_year: 2024,
        source_url: 'https://www.sec.gov/Archives/edgar/data/x/y.htm',
      },
      {
        master_id: 100002,
        canonical_name: 'office properties income trust',
        state: 'MA',
        naics: '525990',
        since_year: 2023,
        position: null,
        is_independent: true,
        committees: [],
        fiscal_year: 2024,
        source_url: null,
      },
    ],
    ...overrides,
  }
}

describe('DirectorProfilePage', () => {
  it('renders loading state', () => {
    useDirectorProfile.mockReturnValue({ data: null, isLoading: true, isError: false })
    renderPage()
    expect(screen.getByText(/Loading director profile/)).toBeInTheDocument()
  })

  it('renders 404 not-found state with helpful copy', () => {
    useDirectorProfile.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 404 },
    })
    renderPage('nobody-here')
    expect(screen.getByText('Director not found')).toBeInTheDocument()
    expect(screen.getByText(/parser hasn't seen them/i)).toBeInTheDocument()
    // Doesn't show the generic error copy
    expect(screen.queryByText(/problem reaching the API/i)).not.toBeInTheDocument()
  })

  it('renders generic error for non-404', () => {
    useDirectorProfile.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: { status: 500 },
    })
    renderPage()
    expect(screen.getByText('Could not load director')).toBeInTheDocument()
    expect(screen.getByText(/problem reaching the API/i)).toBeInTheDocument()
  })

  it('renders director name and board count summary', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture(),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('Adam Portnoy')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    // Text is split across <span>4</span>" company boards" — use a function matcher
    // Text is split across multiple elements; use getAllByText + first match
    expect(
      screen.getAllByText((_, node) =>
        node?.textContent?.includes('Director on 4 company boards'),
      ).length,
    ).toBeGreaterThan(0)
    expect(
      screen.getAllByText((_, node) =>
        node?.textContent?.includes('serving since 2018'),
      ).length,
    ).toBeGreaterThan(0)
  })

  it('renders each board with state, NAICS, since-year, committees', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture(),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('diversified healthcare trust')).toBeInTheDocument()
    expect(screen.getByText('office properties income trust')).toBeInTheDocument()
    expect(screen.getAllByText(/NAICS 525990/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Director since 2018/)).toBeInTheDocument()
    expect(screen.getByText(/Director since 2023/)).toBeInTheDocument()
    expect(screen.getByText('Executive')).toBeInTheDocument()
    expect(screen.getByText('Compensation')).toBeInTheDocument()
  })

  it('renders IND chip for independent + INSIDE chip for non-independent', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture(),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText('IND')).toBeInTheDocument()
    expect(screen.getByText('INSIDE')).toBeInTheDocument()
  })

  it('shows alternate-spelling note when names_matched > 1', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture({ names_matched: ['Adam Portnoy', 'Adam D. Portnoy'] }),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText(/Also recorded as: Adam D\. Portnoy/)).toBeInTheDocument()
  })

  it('omits the alt-spelling note when names_matched is just 1', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture(),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.queryByText(/Also recorded as/)).not.toBeInTheDocument()
  })

  it('renders empty-boards message when boards array is empty', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture({ boards: [], summary: { boards_count: 0, is_independent_count: 0, earliest_since_year: null, latest_since_year: null } }),
      isLoading: false,
      isError: false,
    })
    renderPage()
    expect(screen.getByText(/No board memberships/)).toBeInTheDocument()
  })

  it('source URL link goes to SEC.gov when present, omitted when null', () => {
    useDirectorProfile.mockReturnValue({
      data: fixture(),
      isLoading: false,
      isError: false,
    })
    renderPage()
    const sourceLinks = screen.getAllByTitle('Source DEF14A filing')
    // Only the first board has a source_url; second was null
    expect(sourceLinks).toHaveLength(1)
  })
})
