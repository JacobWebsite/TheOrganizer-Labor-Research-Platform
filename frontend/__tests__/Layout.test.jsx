import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, it, expect, beforeEach } from 'vitest'
import { Layout } from '@/shared/components/Layout'
import { useAuthStore } from '@/shared/stores/authStore'

function renderLayout(initialPath = '/search') {
  useAuthStore.setState({
    user: { username: 'testuser', role: 'admin' },
    token: 'fake',
    isAuthenticated: true,
  })

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="search" element={<div>Search Content</div>} />
          <Route path="targets" element={<div>Targets Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  })

  it('renders the navbar', () => {
    renderLayout()
    expect(screen.getByTestId('navbar')).toBeInTheDocument()
    expect(screen.getByText('The Organizer')).toBeInTheDocument()
  })

  it('renders breadcrumbs on non-hero pages', () => {
    renderLayout('/targets')
    const breadcrumbNav = screen.getByLabelText('Breadcrumb')
    expect(breadcrumbNav).toBeInTheDocument()
    expect(breadcrumbNav).toHaveTextContent('Targets')
  })

  it('hides breadcrumbs on search hero state', () => {
    renderLayout('/search')
    expect(screen.queryByLabelText('Breadcrumb')).not.toBeInTheDocument()
  })

  it('renders the outlet content', () => {
    renderLayout('/search')
    expect(screen.getByText('Search Content')).toBeInTheDocument()
  })

  it('renders different outlet content based on route', () => {
    renderLayout('/targets')
    expect(screen.getByText('Targets Content')).toBeInTheDocument()
  })
})
