import { lazy, Suspense } from 'react'
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
import { PageSkeleton } from '@/shared/components/PageSkeleton'

// Lazy-loaded page components (named export adapter)
const SearchPage = lazy(() => import('@/features/search/SearchPage').then(m => ({ default: m.SearchPage })))
const EmployerProfilePage = lazy(() => import('@/features/employer-profile/EmployerProfilePage').then(m => ({ default: m.EmployerProfilePage })))
const TargetsPage = lazy(() => import('@/features/scorecard/TargetsPage').then(m => ({ default: m.TargetsPage })))
const CompareEmployersPage = lazy(() => import('@/features/scorecard/CompareEmployersPage').then(m => ({ default: m.CompareEmployersPage })))
const UnionsPage = lazy(() => import('@/features/union-explorer/UnionsPage').then(m => ({ default: m.UnionsPage })))
const UnionProfilePage = lazy(() => import('@/features/union-explorer/UnionProfilePage').then(m => ({ default: m.UnionProfilePage })))
const DirectorProfilePage = lazy(() => import('@/features/directors/DirectorProfilePage').then(m => ({ default: m.DirectorProfilePage })))
const SettingsPage = lazy(() => import('@/features/admin/SettingsPage').then(m => ({ default: m.SettingsPage })))
const ResearchPage = lazy(() => import('@/features/research/ResearchPage').then(m => ({ default: m.ResearchPage })))
const ResearchResultPage = lazy(() => import('@/features/research/ResearchResultPage').then(m => ({ default: m.ResearchResultPage })))
const CompareRunsPage = lazy(() => import('@/features/research/CompareRunsPage').then(m => ({ default: m.CompareRunsPage })))
const ResearchReview = lazy(() => import('@/features/research/ResearchReview').then(m => ({ default: m.ResearchReview })))
// UnifiedScorecardPage removed -- /scorecard now redirects to /search
const CBADashboard = lazy(() => import('@/features/cba/CBADashboard').then(m => ({ default: m.CBADashboard })))
const CBADetail = lazy(() => import('@/features/cba/CBADetail').then(m => ({ default: m.CBADetail })))
const CBASearch = lazy(() => import('@/features/cba/CBASearch').then(m => ({ default: m.CBASearch })))
const CBACompare = lazy(() => import('@/features/cba/CBACompare').then(m => ({ default: m.CBACompare })))
const CBAReview = lazy(() => import('@/features/cba/CBAReview').then(m => ({ default: m.CBAReview })))
const CBAArticles = lazy(() => import('@/features/cba/CBAArticles').then(m => ({ default: m.CBAArticles })))

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
                <Route path="search" element={<Suspense fallback={<PageSkeleton />}><SearchPage /></Suspense>} />
                <Route path="employers/:id" element={<Suspense fallback={<PageSkeleton variant="profile" />}><EmployerProfilePage /></Suspense>} />
                <Route path="scorecard" element={<Navigate to="/search" replace />} />
                <Route path="targets" element={<Suspense fallback={<PageSkeleton variant="targets" />}><TargetsPage /></Suspense>} />
                <Route path="compare" element={<Suspense fallback={<PageSkeleton />}><CompareEmployersPage /></Suspense>} />
                <Route path="unions" element={<Suspense fallback={<PageSkeleton variant="unions" />}><UnionsPage /></Suspense>} />
                <Route path="unions/:fnum" element={<Suspense fallback={<PageSkeleton variant="union-profile" />}><UnionProfilePage /></Suspense>} />
                <Route path="directors/:slug" element={<Suspense fallback={<PageSkeleton />}><DirectorProfilePage /></Suspense>} />
                <Route path="research" element={<Suspense fallback={<PageSkeleton variant="research" />}><ResearchPage /></Suspense>} />
                <Route path="research/review" element={<Suspense fallback={<PageSkeleton />}><ResearchReview /></Suspense>} />
                <Route path="research/compare" element={<Suspense fallback={<PageSkeleton />}><CompareRunsPage /></Suspense>} />
                <Route path="research/:runId" element={<Suspense fallback={<PageSkeleton variant="research-result" />}><ResearchResultPage /></Suspense>} />
                <Route path="cbas" element={<Suspense fallback={<PageSkeleton />}><CBADashboard /></Suspense>} />
                <Route path="cbas/search" element={<Suspense fallback={<PageSkeleton />}><CBASearch /></Suspense>} />
                <Route path="cbas/compare" element={<Suspense fallback={<PageSkeleton />}><CBACompare /></Suspense>} />
                <Route path="cbas/review" element={<Suspense fallback={<PageSkeleton />}><CBAReview /></Suspense>} />
                <Route path="cbas/:cbaId" element={<Suspense fallback={<PageSkeleton />}><CBADetail /></Suspense>} />
                <Route path="cbas/:cbaId/articles" element={<Suspense fallback={<PageSkeleton />}><CBAArticles /></Suspense>} />
                <Route path="settings" element={<Suspense fallback={<PageSkeleton />}><SettingsPage /></Suspense>} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AuthChecker>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
