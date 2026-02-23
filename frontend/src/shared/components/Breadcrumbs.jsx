import { Link, useLocation } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

const LABEL_MAP = {
  search: 'Employers',
  employers: 'Employer Profile',
  targets: 'Targets',
  unions: 'Unions',
  settings: 'Settings',
}

export function Breadcrumbs() {
  const location = useLocation()
  const segments = location.pathname.split('/').filter(Boolean)

  if (segments.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted-foreground">
      {segments.map((seg, i) => {
        const path = '/' + segments.slice(0, i + 1).join('/')
        const label = LABEL_MAP[seg] || decodeURIComponent(seg)
        const isLast = i === segments.length - 1

        return (
          <span key={path} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3" />}
            {isLast ? (
              <span className="text-foreground font-medium">{label}</span>
            ) : (
              <Link to={path} className="hover:text-foreground transition-colors">
                {label}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
