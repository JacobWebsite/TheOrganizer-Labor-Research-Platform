import { create } from 'zustand'
import { apiClient } from '@/shared/api/client'

const DEV_BYPASS = import.meta.env.VITE_DISABLE_AUTH === 'true'

function loadUser() {
  if (DEV_BYPASS) return { username: 'dev', role: 'admin' }
  try {
    const raw = localStorage.getItem('auth_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function loadToken() {
  if (DEV_BYPASS) return 'dev-token'
  try {
    return localStorage.getItem('auth_token')
  } catch {
    return null
  }
}

export const useAuthStore = create((set) => ({
  user: loadUser(),
  token: loadToken(),
  isAuthenticated: DEV_BYPASS || !!loadToken(),
  lastActivity: Date.now(),

  touchActivity: () => set({ lastActivity: Date.now() }),

  login: async (username, password) => {
    const data = await apiClient.post('/api/auth/login', { username, password })
    const token = data.access_token
    // Decode payload (JWT is base64url)
    const payload = JSON.parse(atob(token.split('.')[1]))
    const user = { username: payload.sub, role: payload.role || 'user' }

    localStorage.setItem('auth_token', token)
    localStorage.setItem('auth_user', JSON.stringify(user))
    set({ user, token, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    set({ user: null, token: null, isAuthenticated: false })
  },

  // Silent token refresh — called by useAuthCheck when the current token
  // is within ~10 min of expiring. Keeps the session alive as long as
  // the user is still active. Returns the new token on success, throws
  // on failure (caller should logout()). 2026-05-05.
  refreshToken: async () => {
    const data = await apiClient.post('/api/auth/refresh', {})
    const token = data.access_token
    const payload = JSON.parse(atob(token.split('.')[1]))
    const user = { username: payload.sub, role: payload.role || 'user' }
    localStorage.setItem('auth_token', token)
    localStorage.setItem('auth_user', JSON.stringify(user))
    set({ user, token, isAuthenticated: true })
    return token
  },

  isAdmin: () => {
    const user = loadUser()
    return user?.role === 'admin'
  },
}))
