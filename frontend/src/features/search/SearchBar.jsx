import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useEmployerAutocomplete } from '@/shared/api/employers'

/**
 * Search input with autocomplete dropdown.
 * variant="hero" — large centered input (pre-search state)
 * variant="compact" — normal-sized input (post-search state)
 */
export function SearchBar({ variant = 'compact', initialValue = '', onSearch }) {
  const [value, setValue] = useState(initialValue)
  const [debouncedValue, setDebouncedValue] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(-1)
  const wrapperRef = useRef(null)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  // Sync external initial value changes (e.g. URL back/forward)
  useEffect(() => {
    setValue(initialValue)
  }, [initialValue])

  // Debounce input for autocomplete
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), 300)
    return () => clearTimeout(timer)
  }, [value])

  const { data } = useEmployerAutocomplete(debouncedValue.length >= 3 ? debouncedValue : '')
  const suggestions = data?.employers || []

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSubmit = useCallback((e) => {
    e.preventDefault()
    setIsOpen(false)
    onSearch(value.trim())
  }, [value, onSearch])

  const handleSelect = useCallback((employer) => {
    setIsOpen(false)
    navigate(`/employers/${employer.canonical_id}`)
  }, [navigate])

  const handleKeyDown = useCallback((e) => {
    if (!isOpen || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIndex((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIndex((i) => Math.max(i - 1, -1))
    } else if (e.key === 'Enter' && highlightIndex >= 0) {
      e.preventDefault()
      handleSelect(suggestions[highlightIndex])
    } else if (e.key === 'Escape') {
      setIsOpen(false)
    }
  }, [isOpen, suggestions, highlightIndex, handleSelect])

  const isHero = variant === 'hero'

  return (
    <div ref={wrapperRef} className="relative w-full">
      <form onSubmit={handleSubmit} role="search">
        <div className="relative">
          <Search className={cn(
            'absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground',
            isHero ? 'h-5 w-5' : 'h-4 w-4'
          )} />
          <Input
            ref={inputRef}
            type="text"
            placeholder="Check if an employer has a union"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setIsOpen(true)
              setHighlightIndex(-1)
            }}
            onFocus={() => { if (suggestions.length > 0) setIsOpen(true) }}
            onKeyDown={handleKeyDown}
            className={cn(
              isHero ? 'h-14 pl-11 text-lg shadow-md shadow-[#d9cebb]/50' : 'h-10 pl-9 text-sm'
            )}
          />
        </div>
      </form>

      {/* Autocomplete dropdown */}
      {isOpen && suggestions.length > 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border bg-popover shadow-lg">
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b bg-muted/30">
            Employers
          </div>
          {suggestions.map((emp, i) => (
            <button
              key={emp.canonical_id}
              type="button"
              className={cn(
                'flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-accent text-left',
                i === highlightIndex && 'bg-accent'
              )}
              onMouseDown={() => handleSelect(emp)}
              onMouseEnter={() => setHighlightIndex(i)}
            >
              <span className="font-medium truncate">{emp.employer_name}</span>
              <span className="text-muted-foreground text-xs ml-2 shrink-0">
                {[emp.city, emp.state].filter(Boolean).join(', ')}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
