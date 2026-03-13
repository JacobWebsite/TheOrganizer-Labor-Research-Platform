import { useState, useEffect, useRef } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { Search, Target, Users, Microscope, Settings, LogOut, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/shared/stores/authStore'

const NAV_ITEMS = [
  { to: '/search', label: 'Search', icon: Search },
  { to: '/targets', label: 'Targets', icon: Target },
  { to: '/unions', label: 'Unions', icon: Users },
  { to: '/research', label: 'Research', icon: Microscope },
  { to: '/cbas', label: 'Contracts', icon: FileText },
]

const ADMIN_ITEM = { to: '/settings', label: 'Settings', icon: Settings }

export function NavBar({ onOpenPalette }) {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const isAdmin = user?.role === 'admin'

  // Auto-hide on scroll
  const [visible, setVisible] = useState(true)
  const lastScrollY = useRef(0)

  useEffect(() => {
    function onScroll() {
      const currentY = window.scrollY
      if (currentY > lastScrollY.current && currentY > 64) {
        setVisible(false)
      } else {
        setVisible(true)
      }
      lastScrollY.current = currentY
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const items = isAdmin ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS

  return (
    <nav
      data-testid="navbar"
      data-no-print
      className={cn(
        'fixed top-0 left-0 right-0 z-50 transition-transform duration-200',
        visible ? 'translate-y-0' : '-translate-y-full'
      )}
      style={{ backgroundColor: '#2c2418' }}
    >
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <span className="font-editorial text-xl font-bold tracking-tight" style={{ color: '#faf6ef' }}>
            The Organizer
          </span>
          <div className="flex items-center gap-1">
            {items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors border-b-2',
                    isActive
                      ? 'border-[#c78c4e] text-[#c78c4e]'
                      : 'border-transparent text-[#faf6ef]/60 hover:text-[#faf6ef]/90'
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {onOpenPalette && (
            <button
              type="button"
              onClick={onOpenPalette}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded border border-[#faf6ef]/20 text-[#faf6ef]/50 hover:text-[#faf6ef]/80 hover:border-[#faf6ef]/40 transition-colors"
            >
              Quick Jump...
              <kbd className="text-[10px] font-mono px-1 py-0.5 rounded bg-[#faf6ef]/10 text-[#faf6ef]/40">
                {navigator?.platform?.includes('Mac') ? '\u2318' : 'Ctrl'}K
              </kbd>
            </button>
          )}
          <span className="text-sm" style={{ color: 'rgba(250,246,239,0.6)' }}>{user?.username}</span>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 text-sm transition-colors"
            style={{ color: 'rgba(250,246,239,0.6)' }}
            onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(250,246,239,0.9)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(250,246,239,0.6)'}
            aria-label="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </nav>
  )
}
