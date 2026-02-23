import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

// Mock admin API hooks
vi.mock('@/shared/api/admin', () => ({
  useSystemHealth: vi.fn(() => ({ data: null, isLoading: false })),
  usePlatformStats: vi.fn(() => ({ data: null, isLoading: false })),
  useDataFreshness: vi.fn(() => ({ data: null, isLoading: false })),
  useScoreVersions: vi.fn(() => ({ data: null, isLoading: false })),
  useMatchQuality: vi.fn(() => ({ data: null, isLoading: false })),
  useMatchReview: vi.fn(() => ({ data: null, isLoading: false })),
  useRefreshScorecard: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRefreshFreshness: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useReviewMatch: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRegisterUser: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

// Mock auth store
vi.mock('@/shared/stores/authStore', () => ({
  useAuthStore: vi.fn(),
}))

import {
  useSystemHealth,
  usePlatformStats,
  useDataFreshness,
  useMatchQuality,
  useMatchReview,
} from '@/shared/api/admin'
import { useAuthStore } from '@/shared/stores/authStore'
import { SettingsPage } from '@/features/admin/SettingsPage'

const MOCK_HEALTH = { status: 'ok', db: true, timestamp: '2026-02-22T12:00:00Z' }
const MOCK_STATS = { total_employers: 146863, total_scorecard_rows: 146863, match_counts_by_source: [{ source_system: 'osha', match_count: 97142 }] }
const MOCK_FRESHNESS = { sources: [
  { source_name: 'osha', row_count: 97142, latest_record_date: '2026-02-20', stale: false },
  { source_name: 'nlrb', row_count: 25879, latest_record_date: '2026-01-15', stale: true },
] }
const MOCK_QUALITY = { total_match_rows: 1738115, by_source: [{ source_system: 'osha', total_rows: 97142 }], by_confidence: [{ confidence_band: 'HIGH', total_rows: 500000 }] }
const MOCK_REVIEW = { matches: [], total: 0 }

function setAdmin() {
  useAuthStore.mockImplementation((selector) => {
    const state = { user: { username: 'admin', role: 'admin' }, token: 'test', isAuthenticated: true }
    return selector(state)
  })
}

function setNonAdmin() {
  useAuthStore.mockImplementation((selector) => {
    const state = { user: { username: 'user1', role: 'user' }, token: 'test', isAuthenticated: true }
    return selector(state)
  })
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SettingsPage', () => {
  beforeEach(() => {
    useSystemHealth.mockReturnValue({ data: null, isLoading: false })
    usePlatformStats.mockReturnValue({ data: null, isLoading: false })
    useDataFreshness.mockReturnValue({ data: null, isLoading: false })
    useMatchQuality.mockReturnValue({ data: null, isLoading: false })
    useMatchReview.mockReturnValue({ data: null, isLoading: false })
    setAdmin()
  })

  it('shows access denied for non-admin user', () => {
    setNonAdmin()
    renderPage()
    expect(screen.getByText('Access Denied')).toBeInTheDocument()
    expect(screen.getByText('You need admin privileges to view this page.')).toBeInTheDocument()
  })

  it('renders page title for admin user', () => {
    renderPage()
    expect(screen.getByText('Administration')).toBeInTheDocument()
  })

  it('shows health status with green dots when healthy', () => {
    useSystemHealth.mockReturnValue({ data: MOCK_HEALTH, isLoading: false })
    renderPage()
    expect(screen.getByText('System Health')).toBeInTheDocument()
    const healthyLabels = screen.getAllByText('Healthy')
    expect(healthyLabels.length).toBe(2) // API + Database
    const greenDots = document.querySelectorAll('.bg-green-500')
    expect(greenDots.length).toBe(2)
  })

  it('shows platform stats', () => {
    usePlatformStats.mockReturnValue({ data: MOCK_STATS, isLoading: false })
    renderPage()
    expect(screen.getByText('Platform Statistics')).toBeInTheDocument()
    // 146,863 appears twice (total_employers and total_scorecard_rows are the same value)
    const statValues = screen.getAllByText('146,863')
    expect(statValues.length).toBe(2)
    // Total matches computed from match_counts_by_source sum (97,142)
    expect(screen.getByText('97,142')).toBeInTheDocument()
  })

  it('shows freshness table with source data', () => {
    useDataFreshness.mockReturnValue({ data: MOCK_FRESHNESS, isLoading: false })
    renderPage()
    expect(screen.getByText('Data Freshness')).toBeInTheDocument()
    expect(screen.getByText('osha')).toBeInTheDocument()
    expect(screen.getByText('nlrb')).toBeInTheDocument()
    expect(screen.getByText('Fresh')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
  })

  it('renders match review section', () => {
    useMatchReview.mockReturnValue({ data: MOCK_REVIEW, isLoading: false })
    renderPage()
    expect(screen.getByText('Match Review')).toBeInTheDocument()
    expect(screen.getByText(/All clear/)).toBeInTheDocument()
  })

  it('renders refresh buttons', () => {
    renderPage()
    expect(screen.getByText('Maintenance Actions')).toBeInTheDocument()
    expect(screen.getByText('Refresh Scorecard')).toBeInTheDocument()
    expect(screen.getByText('Refresh Freshness')).toBeInTheDocument()
  })
})
