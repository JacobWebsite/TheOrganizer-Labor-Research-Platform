import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, beforeEach } from 'vitest'
import { NavBar } from '@/shared/components/NavBar'
import { useAuthStore } from '@/shared/stores/authStore'

function renderNavBar(user = { username: 'testuser', role: 'user' }) {
  useAuthStore.setState({ user, isAuthenticated: true })
  return render(
    <MemoryRouter>
      <NavBar />
    </MemoryRouter>
  )
}

describe('NavBar', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  })

  it('renders the app title', () => {
    renderNavBar()
    expect(screen.getByText('The Organizer')).toBeInTheDocument()
  })

  it('renders main navigation tabs', () => {
    renderNavBar()
    expect(screen.getByText('Employers')).toBeInTheDocument()
    expect(screen.getByText('Targets')).toBeInTheDocument()
    expect(screen.getByText('Unions')).toBeInTheDocument()
  })

  it('hides Settings tab for non-admin users', () => {
    renderNavBar({ username: 'regular', role: 'user' })
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
  })

  it('shows Settings tab for admin users', () => {
    renderNavBar({ username: 'admin', role: 'admin' })
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('displays the username', () => {
    renderNavBar({ username: 'jdoe', role: 'user' })
    expect(screen.getByText('jdoe')).toBeInTheDocument()
  })
})
