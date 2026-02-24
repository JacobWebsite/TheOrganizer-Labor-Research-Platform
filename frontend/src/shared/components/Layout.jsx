import { Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { NavBar } from './NavBar'
import { Breadcrumbs } from './Breadcrumbs'

export function Layout() {
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()

  // Hide breadcrumbs on search page when no query is active (hero state)
  const isSearchHero = pathname === '/search' && !Array.from(searchParams).length

  return (
    <div className="min-h-screen bg-background">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:text-sm">
        Skip to main content
      </a>
      <NavBar />
      <main id="main-content" className="mx-auto max-w-7xl px-4 pt-20 pb-8">
        {!isSearchHero && (
          <div className="mb-4">
            <Breadcrumbs />
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
