import { useEffect } from 'react'
import { useAuthStore } from '@/shared/stores/authStore'

const SESSION_TIMEOUT_MS = 60 * 60 * 1000 // 1 hour
const CHECK_INTERVAL_MS = 60_000 // check every minute

/**
 * Hook that checks token expiry and inactivity timeout every 60 seconds.
 * Tracks user activity (clicks, keystrokes, scrolls) to reset the sliding window.
 */
export function useAuthCheck() {
  const logout = useAuthStore((s) => s.logout)
  const token = useAuthStore((s) => s.token)
  const touchActivity = useAuthStore((s) => s.touchActivity)

  // Track user activity
  useEffect(() => {
    if (!token || token === 'dev-token') return

    function onActivity() {
      touchActivity()
    }

    window.addEventListener('click', onActivity)
    window.addEventListener('keydown', onActivity)
    window.addEventListener('scroll', onActivity, { passive: true })

    return () => {
      window.removeEventListener('click', onActivity)
      window.removeEventListener('keydown', onActivity)
      window.removeEventListener('scroll', onActivity)
    }
  }, [token, touchActivity])

  // Check token expiry + inactivity
  useEffect(() => {
    if (!token || token === 'dev-token') return

    function check() {
      // Token expiry check
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        if (payload.exp && payload.exp * 1000 < Date.now()) {
          logout()
          return
        }
      } catch {
        logout()
        return
      }

      // Inactivity timeout check
      const lastActivity = useAuthStore.getState().lastActivity
      if (Date.now() - lastActivity > SESSION_TIMEOUT_MS) {
        logout()
      }
    }

    check()
    const interval = setInterval(check, CHECK_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [token, logout])
}
