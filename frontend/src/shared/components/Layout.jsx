import { useState, useEffect, useCallback } from 'react'
import { Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { NavBar } from './NavBar'
import { Breadcrumbs } from './Breadcrumbs'
import { CommandPalette } from './CommandPalette'

export function Layout() {
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const [isPaletteOpen, setIsPaletteOpen] = useState(false)

  // Hide breadcrumbs on search page when no query is active (hero state)
  const isSearchHero = pathname === '/search' && !Array.from(searchParams).length

  // Ctrl+K / Cmd+K keyboard shortcut
  const handleKeyDown = useCallback((e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      setIsPaletteOpen((v) => !v)
    }
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="min-h-screen bg-background">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:text-sm">
        Skip to main content
      </a>
      <NavBar onOpenPalette={() => setIsPaletteOpen(true)} />
      <main id="main-content" className="mx-auto max-w-7xl px-4 pt-20 pb-8">
        {!isSearchHero && (
          <div className="mb-4">
            <Breadcrumbs />
          </div>
        )}
        <Outlet />
      </main>
      {isPaletteOpen && (
        <CommandPalette isOpen={isPaletteOpen} onClose={() => setIsPaletteOpen(false)} />
      )}
    </div>
  )
}
