import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, it, expect, beforeEach } from 'vitest'
import { ProtectedRoute } from '@/shared/components/ProtectedRoute'
import { useAuthStore } from '@/shared/stores/authStore'

function renderWithRoute(isAuthenticated) {
  useAuthStore.setState({
    user: isAuthenticated ? { username: 'test', role: 'user' } : null,
    token: isAuthenticated ? 'fake-token' : null,
    isAuthenticated,
  })

  return render(
    <MemoryRouter initialEntries={['/protected']}>
      <Routes>
        <Route path="/login" element={<div>Login Page</div>} />
        <Route
          path="/protected"
          element={
            <ProtectedRoute>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  })

  it('redirects unauthenticated users to login', () => {
    renderWithRoute(false)
    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders children for authenticated users', () => {
    renderWithRoute(true)
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })
})
