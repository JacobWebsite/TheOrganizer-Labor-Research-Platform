import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { queryClient } from '@/shared/api/queryClient'
import { useAuthCheck } from '@/shared/hooks/useAuth'
import { ErrorBoundary } from '@/shared/components/ErrorBoundary'
import { Layout } from '@/shared/components/Layout'
import { ProtectedRoute } from '@/shared/components/ProtectedRoute'
import { NotFound } from '@/shared/components/NotFound'
import { LoginPage } from '@/features/auth/LoginPage'
import { SearchPage } from '@/features/search/SearchPage'
import { EmployerProfilePage } from '@/features/employer-profile/EmployerProfilePage'
import { TargetsPage } from '@/features/scorecard/TargetsPage'
import { UnionsPage } from '@/features/union-explorer/UnionsPage'
import { UnionProfilePage } from '@/features/union-explorer/UnionProfilePage'
import { SettingsPage } from '@/features/admin/SettingsPage'
import { ResearchPage } from '@/features/research/ResearchPage'
import { ResearchResultPage } from '@/features/research/ResearchResultPage'

function AuthChecker({ children }) {
  useAuthCheck()
  return children
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <AuthChecker>
            <Toaster position="top-right" />
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Navigate to="/search" replace />} />
                <Route path="search" element={<SearchPage />} />
                <Route path="employers/:id" element={<EmployerProfilePage />} />
                <Route path="targets" element={<TargetsPage />} />
                <Route path="unions" element={<UnionsPage />} />
                <Route path="unions/:fnum" element={<UnionProfilePage />} />
                <Route path="research" element={<ResearchPage />} />
                <Route path="research/:runId" element={<ResearchResultPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AuthChecker>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
