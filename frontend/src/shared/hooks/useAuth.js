import { useEffect } from 'react'
import { useAuthStore } from '@/shared/stores/authStore'

const SESSION_TIMEOUT_MS = 60 * 60 * 1000 // 1 hour of inactivity before logout
const CHECK_INTERVAL_MS = 60_000 // check every minute
// 2026-05-05: backend JWT lifetime dropped 8h -> 1h. Trigger a silent
// refresh when the current token has this many ms left, so a stable
// network always has time to retry before the user notices anything.
const REFRESH_BEFORE_EXPIRY_MS = 10 * 60 * 1000 // 10 min
// Track refresh-in-flight at module scope so we don't fire concurrent
// refresh requests when the check tick races with hot-reload remounts
// or multiple consumers of this hook.
let _refreshInFlight = null

/**
 * Hook that:
 *  - tracks user activity (clicks, keystrokes, scrolls) to reset the
 *    sliding inactivity window
 *  - checks token expiry every 60 seconds
 *  - silently refreshes the token via /api/auth/refresh when it has
 *    < 10 min of life left
 *  - logs the user out on hard expiry, refresh failure, or 1 hour of
 *    inactivity
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

  // Check token expiry + auto-refresh + inactivity
  useEffect(() => {
    if (!token || token === 'dev-token') return

    function check() {
      // Read the LATEST token from the store, not the closure-captured
      // one — refreshToken() may have replaced it since this effect ran.
      const currentToken = useAuthStore.getState().token
      if (!currentToken || currentToken === 'dev-token') return

      // Decode JWT payload to read the exp claim.
      let expMs = null
      try {
        const payload = JSON.parse(atob(currentToken.split('.')[1]))
        if (payload.exp) expMs = payload.exp * 1000
      } catch {
        // Malformed token — treat as expired.
        logout()
        return
      }

      // Hard expiry — token is already dead, kick the user out.
      if (expMs && expMs < Date.now()) {
        logout()
        return
      }

      // Inactivity timeout check (independent of token life). If the user
      // hasn't clicked/typed/scrolled in an hour, log them out even if the
      // token is still valid.
      const lastActivity = useAuthStore.getState().lastActivity
      if (Date.now() - lastActivity > SESSION_TIMEOUT_MS) {
        logout()
        return
      }

      // Silent-refresh window: token is still valid but expiring soon.
      // Only one refresh in flight at a time (across remounts / multiple
      // tabs sharing this hook).
      if (expMs && expMs - Date.now() < REFRESH_BEFORE_EXPIRY_MS) {
        if (_refreshInFlight) return
        const refreshToken = useAuthStore.getState().refreshToken
        if (!refreshToken) return
        _refreshInFlight = refreshToken()
          .catch(() => {
            // Refresh failed (server rejected, network down, user
            // deactivated, JWT secret rotated). Treat like a hard
            // expiry — kick the user back to login.
            logout()
          })
          .finally(() => {
            _refreshInFlight = null
          })
      }
    }

    check()
    const interval = setInterval(check, CHECK_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [token, logout])
}
