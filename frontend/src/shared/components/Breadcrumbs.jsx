import { Link, useLocation } from 'react-router-dom'

const LABEL_MAP = {
  search: 'Employers',
  employers: 'Employer Profile',
  targets: 'Targets',
  unions: 'Unions',
  research: 'Research',
  settings: 'Settings',
}

/**
 * Enhanced breadcrumbs with clickable navigation trail.
 *
 * Can be used in two modes:
 * 1. Auto-generated from URL path (default, when no `items` prop)
 * 2. Custom items array: [{ label: "Search", to: "/search" }, { label: "Walmart" }]
 *    The last item (no `to` or `onClick`) is rendered as the current page.
 */
export function Breadcrumbs({ items }) {
  const location = useLocation()

  // If custom items provided, use those; otherwise generate from URL
  const crumbs = items || generateCrumbs(location.pathname)

  if (crumbs.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-0 text-xs py-2.5 px-0">
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1

        return (
          <span key={crumb.label + i} className="flex items-center">
            {i > 0 && (
              <span className="mx-1.5 text-[#d9cebb]" aria-hidden>&rsaquo;</span>
            )}
            {isLast ? (
              <span className="text-[#2c2418] font-semibold">{crumb.label}</span>
            ) : crumb.to ? (
              <Link
                to={crumb.to}
                className="text-[#8a7e6d] underline decoration-[#d9cebb] underline-offset-2 hover:text-[#2c2418] transition-colors"
              >
                {crumb.label}
              </Link>
            ) : crumb.onClick ? (
              <button
                type="button"
                onClick={crumb.onClick}
                className="text-[#8a7e6d] underline decoration-[#d9cebb] underline-offset-2 hover:text-[#2c2418] transition-colors cursor-pointer"
              >
                {crumb.label}
              </button>
            ) : (
              <span className="text-[#8a7e6d]">{crumb.label}</span>
            )}
          </span>
        )
      })}
    </nav>
  )
}

function generateCrumbs(pathname) {
  const segments = pathname.split('/').filter(Boolean)
  if (segments.length === 0) return []

  return segments.map((seg, i) => {
    const path = '/' + segments.slice(0, i + 1).join('/')
    const label = LABEL_MAP[seg] || decodeURIComponent(seg)
    const isLast = i === segments.length - 1

    return {
      label,
      to: isLast ? undefined : path,
    }
  })
}
