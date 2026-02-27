/**
 * API client — thin fetch wrapper with auth token injection and error handling.
 */

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail || data?.message || `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

function getToken() {
  try {
    return localStorage.getItem('auth_token')
  } catch {
    return null
  }
}

export async function apiClient(url, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401 && import.meta.env.VITE_DISABLE_AUTH !== 'true') {
    // Auto-logout on unauthorized
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    window.location.href = '/login'
    throw new ApiError(401, { detail: 'Session expired' })
  }

  if (!response.ok) {
    let data
    try {
      data = await response.json()
    } catch {
      data = { detail: response.statusText }
    }
    throw new ApiError(response.status, data)
  }

  if (response.status === 204) return null
  return response.json()
}

// Convenience methods
apiClient.get = (url) => apiClient(url)
apiClient.post = (url, body) => apiClient(url, { method: 'POST', body: JSON.stringify(body) })
apiClient.put = (url, body) => apiClient(url, { method: 'PUT', body: JSON.stringify(body) })
apiClient.delete = (url) => apiClient(url, { method: 'DELETE' })
