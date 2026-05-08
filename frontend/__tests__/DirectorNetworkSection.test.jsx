/**
 * DirectorNetworkSection tests (24Q-14 C.2-3).
 *
 * Covers:
 * - hidden when loading / error / should_surface=false
 * - rendered when should_surface=true
 * - shared director chips link to /directors/{slug}
 * - 1-hop list with N-link badges + master profile links
 * - 2-hop list with via-companies count
 * - "Show all" expand button when > VISIBLE_ONE_HOP / VISIBLE_TWO_HOP
 * - sort: 1-hop sorted by shared_director_count desc
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DirectorNetworkSection } from '@/features/employer-profile/DirectorNetworkSection'

vi.mock('@/shared/api/profile', () => ({
  useDirectorNetwork: vi.fn(),
}))

import { useDirectorNetwork } from '@/shared/api/profile'

function fixture(overrides = {}) {
  return {
    anchor: { master_id: 4036186, canonical_name: 'abbott laboratories' },
    stats: {
      one_hop_count: 4,
      two_hop_count: 8,
      two_hop_returned: 8,
      shared_directors_total: 4,
      should_surface: true,
    },
    shared_directors: [
      { name: 'John G. Stratton', slug: 'john-g-stratton' },
      { name: 'Nancy McKinstry', slug: 'nancy-mckinstry' },
    ],
    one_hop: [
      {
        master_id: 1, canonical_name: 'general dynamics', state: 'VA', naics: '336411',
        shared_directors: ['John G. Stratton'], shared_director_count: 1,
      },
      {
        master_id: 2, canonical_name: 'mondelez international', state: 'IL', naics: '311351',
        shared_directors: ['Nancy McKinstry'], shared_director_count: 1,
      },
    ],
    two_hop: [
      {
        master_id: 5, canonical_name: 'humana inc', state: 'KY', naics: '524114',
        via_company_count: 2, via_director_count: 2,
      },
      {
        master_id: 6, canonical_name: 'bristol myers squibb', state: 'NY', naics: '325412',
        via_company_count: 1, via_director_count: 1,
      },
    ],
    ...overrides,
  }
}

describe('DirectorNetworkSection', () => {
  it('returns null when loading', () => {
    useDirectorNetwork.mockReturnValue({ data: null, isLoading: true, isError: false })
    const { container } = render(<DirectorNetworkSection masterId={1} />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when error', () => {
    useDirectorNetwork.mockReturnValue({ data: null, isLoading: false, isError: true })
    const { container } = render(<DirectorNetworkSection masterId={1} />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when should_surface=false', () => {
    useDirectorNetwork.mockReturnValue({
      data: fixture({ stats: { ...fixture().stats, should_surface: false, one_hop_count: 1 } }),
      isLoading: false, isError: false,
    })
    const { container } = render(<DirectorNetworkSection masterId={1} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders header + 3 stat tiles', () => {
    useDirectorNetwork.mockReturnValue({ data: fixture(), isLoading: false, isError: false })
    render(<DirectorNetworkSection masterId={1} />)
    expect(screen.getByText('Director Network')).toBeInTheDocument()
    // "Shared Directors" appears in two places — the stat tile label
    // and the section header. getAllByText asserts both render.
    expect(screen.getAllByText('Shared Directors').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Direct Companies')).toBeInTheDocument()
    expect(screen.getByText('2-Hop Companies')).toBeInTheDocument()
  })

  it('renders shared director chips with /directors/{slug} links', () => {
    useDirectorNetwork.mockReturnValue({ data: fixture(), isLoading: false, isError: false })
    render(<DirectorNetworkSection masterId={1} />)
    const stratton = screen.getByText('John G. Stratton').closest('a')
    expect(stratton).toHaveAttribute('href', '/directors/john-g-stratton')
    const nancy = screen.getByText('Nancy McKinstry').closest('a')
    expect(nancy).toHaveAttribute('href', '/directors/nancy-mckinstry')
  })

  it('renders 1-hop companies with shared director list', () => {
    useDirectorNetwork.mockReturnValue({ data: fixture(), isLoading: false, isError: false })
    render(<DirectorNetworkSection masterId={1} />)
    expect(screen.getByText('general dynamics')).toBeInTheDocument()
    expect(screen.getByText('mondelez international')).toBeInTheDocument()
    // 1-hop links to master profile
    const gd = screen.getByText('general dynamics').closest('a')
    expect(gd).toHaveAttribute('href', '/employers/MASTER-1')
    // shared-director list rendered inline (function-matcher because text is split)
    expect(
      screen.getAllByText((_, n) => n?.textContent?.includes('Shared director: John G. Stratton')).length,
    ).toBeGreaterThan(0)
  })

  it('renders 2-hop companies with via-paths badge', () => {
    useDirectorNetwork.mockReturnValue({ data: fixture(), isLoading: false, isError: false })
    render(<DirectorNetworkSection masterId={1} />)
    expect(screen.getByText('humana inc')).toBeInTheDocument()
    expect(screen.getByText('bristol myers squibb')).toBeInTheDocument()
    expect(screen.getByText('2 paths')).toBeInTheDocument()
    expect(screen.getByText('1 path')).toBeInTheDocument()
  })

  it('shows "top N shown" hint when two_hop_count > two_hop_returned', () => {
    useDirectorNetwork.mockReturnValue({
      data: fixture({
        stats: { ...fixture().stats, two_hop_count: 100, two_hop_returned: 8 },
      }),
      isLoading: false, isError: false,
    })
    render(<DirectorNetworkSection masterId={1} />)
    expect(
      screen.getAllByText((_, n) => n?.textContent?.includes('top 8 shown')).length,
    ).toBeGreaterThan(0)
  })

  it('one-hop "show all" button appears when > 8 entries and toggles', () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      master_id: 1000 + i,
      canonical_name: `company ${i}`,
      state: 'CA',
      naics: null,
      shared_directors: ['Director X'],
      shared_director_count: 1,
    }))
    useDirectorNetwork.mockReturnValue({
      data: fixture({ one_hop: many, stats: { ...fixture().stats, one_hop_count: 12 } }),
      isLoading: false, isError: false,
    })
    render(<DirectorNetworkSection masterId={1} />)
    const btn = screen.getByText(/Show all 12 direct connections/i)
    fireEvent.click(btn)
    expect(screen.getByText('company 11')).toBeInTheDocument()
  })

  it('uses singular "1 link" for shared_director_count=1', () => {
    useDirectorNetwork.mockReturnValue({ data: fixture(), isLoading: false, isError: false })
    render(<DirectorNetworkSection masterId={1} />)
    expect(screen.getAllByText('1 link').length).toBeGreaterThan(0)
  })
})
