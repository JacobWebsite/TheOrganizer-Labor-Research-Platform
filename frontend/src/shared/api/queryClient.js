import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: (failureCount, error) => {
        // Don't retry on 401 (unauthorized) or 404 (not found)
        if (error?.status === 401 || error?.status === 404) return false
        return failureCount < 2
      },
    },
  },
})
