import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useEmployerAutocomplete } from '@/shared/api/employers'

const QUICK_LINKS = [
  { label: 'Search', path: '/search', icon: 'search' },
  { label: 'Targets', path: '/targets', icon: 'page' },
  { label: 'Unions', path: '/unions', icon: 'page' },
  { label: 'Research', path: '/research', icon: 'page' },
  { label: 'Settings', path: '/settings', icon: 'page' },
]

export function CommandPalette({ isOpen, onClose }) {
  const [query, setQuery] = useState('')
  const inputRef = useRef(null)
  const navigate = useNavigate()

  // Only query when palette is open and query is long enough
  const { data: autocompleteData } = useEmployerAutocomplete(
    isOpen && query.length >= 2 ? query : ''
  )

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  const handleSelect = useCallback((path) => {
    navigate(path)
    onClose()
  }, [navigate, onClose])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose()
    }
  }, [onClose])

  if (!isOpen) return null

  // Build results list
  const results = []

  // Employer matches from autocomplete
  const employers = autocompleteData?.results || autocompleteData || []
  if (Array.isArray(employers)) {
    for (const emp of employers.slice(0, 6)) {
      const id = emp.employer_id || emp.id || emp.canonical_id
      const name = emp.employer_name || emp.display_name || emp.name
      if (id && name) {
        results.push({
          key: `emp-${id}`,
          label: name,
          sub: [emp.city, emp.state].filter(Boolean).join(', '),
          icon: 'employer',
          path: `/employers/${id}`,
        })
      }
    }
  }

  // Quick links (filtered by query)
  const filteredLinks = query
    ? QUICK_LINKS.filter(l => l.label.toLowerCase().includes(query.toLowerCase()))
    : QUICK_LINKS
  for (const link of filteredLinks) {
    results.push({
      key: `link-${link.path}`,
      label: link.label,
      sub: null,
      icon: link.icon,
      path: link.path,
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Palette */}
      <div
        className="relative bg-[#faf6ef] rounded-xl w-[520px] max-h-[400px] shadow-2xl border border-[#d9cebb] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#d9cebb]">
          <Search className="h-4 w-4 text-[#8a7e6d] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search employers, unions, or jump to a page..."
            className="flex-1 bg-transparent font-editorial text-[15px] text-[#2c2418] placeholder:text-[#8a7e6d] outline-none"
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-[#8a7e6d] border border-[#d9cebb] rounded bg-[#ede7db]">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[320px] overflow-y-auto">
          {results.length === 0 && query.length >= 2 && (
            <p className="px-4 py-6 text-sm text-[#8a7e6d] text-center">No results found</p>
          )}
          {results.map((item, i) => (
            <button
              key={item.key}
              type="button"
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[#ede7db] transition-colors cursor-pointer ${
                i === 0 ? 'bg-[#ede7db]/50' : ''
              }`}
              onClick={() => handleSelect(item.path)}
            >
              <span className="text-sm shrink-0">
                {item.icon === 'employer' ? '🏢' : item.icon === 'search' ? '🔍' : '📄'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[#2c2418] truncate">{item.label}</p>
                {item.sub && (
                  <p className="text-[11px] text-[#8a7e6d] truncate">{item.sub}</p>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
