/**
 * BasicProfileView (Identity card) polish-sweep tests (Week 4 A.3).
 *
 * Confirms the four standard states render distinctly:
 * - Loading: skeleton outline of header + quality strip
 * - Error: amber retry panel calling onRetry
 * - Empty: "No identity data is available" amber panel (data resolved but
 *   has no usable name field)
 * - Partial / populated: name + sourceType display with the existing
 *   "Limited data" advisory copy
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { BasicProfileView } from '@/features/employer-profile/BasicProfileView'

function renderCard(props) {
  return render(
    <MemoryRouter>
      <BasicProfileView {...props} />
    </MemoryRouter>,
  )
}

describe('BasicProfileView states', () => {
  it('renders loading skeleton when isLoading=true', () => {
    const { container } = renderCard({ isLoading: true })
    expect(container.querySelector('[data-testid="identity-card-skeleton"]')).not.toBeNull()
    expect(screen.queryByText(/No identity data is available/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Could not load employer identity/)).not.toBeInTheDocument()
  })

  it('renders error state with retry button calling onRetry', () => {
    const onRetry = vi.fn()
    renderCard({ isError: true, onRetry })
    expect(screen.getByText(/Could not load employer identity/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders empty state when data resolves but has no usable name', () => {
    renderCard({
      data: {
        employer: { unit_city: 'Nowhere' },
        source_type: 'NLRB',
      },
    })
    expect(screen.getByText(/No identity data is available/)).toBeInTheDocument()
  })

  it('renders empty state for master path when canonical_name + display_name are missing', () => {
    renderCard({
      data: {
        master: { master_id: 999 },
        source_ids: [],
      },
      isMaster: true,
    })
    expect(screen.getByText(/No identity data is available/)).toBeInTheDocument()
  })

  it('renders populated path with name + Limited Data advisory', () => {
    renderCard({
      data: {
        employer: {
          participant_name: 'Some Co',
          unit_city: 'Boston',
          unit_state: 'MA',
        },
        source_type: 'NLRB',
        cross_references: [],
      },
    })
    expect(screen.getByText('Some Co')).toBeInTheDocument()
    expect(screen.getByText(/Limited data is available/)).toBeInTheDocument()
  })
})
