import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { LoginPage } from '@/features/auth/LoginPage'
import { useAuthStore } from '@/shared/stores/authStore'

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  })

  it('renders the login form', () => {
    renderLogin()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('renders the app title', () => {
    renderLogin()
    expect(screen.getByText('THE ORGANIZER')).toBeInTheDocument()
  })

  it('renders sign-in messaging', () => {
    renderLogin()
    expect(screen.getByText(/sign in to your account/i)).toBeInTheDocument()
  })

  it('shows error on failed login', async () => {
    // Mock the login to reject
    const mockLogin = vi.fn().mockRejectedValue(new Error('Invalid credentials'))
    useAuthStore.setState({ login: mockLogin })

    renderLogin()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'bad' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials')
    })
  })

  it('calls login on form submit', async () => {
    const mockLogin = vi.fn().mockResolvedValue(undefined)
    useAuthStore.setState({ login: mockLogin })

    renderLogin()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'user1' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pass1' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('user1', 'pass1')
    })
  })
})
