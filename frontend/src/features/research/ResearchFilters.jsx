import { useRef } from 'react'
import { Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export function ResearchFilters({ filters, hasActiveFilters, onSetFilter, onClearFilter, onClearAll }) {
  const debounceRef = useRef(null)

  function handleSearch(e) {
    const value = e.target.value
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      onSetFilter('q', value)
    }, 300)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          defaultValue={filters.q}
          onChange={handleSearch}
          placeholder="Search by company name..."
          className="h-10 w-full border border-input bg-background pl-9 pr-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <Select
        value={filters.status}
        onChange={(e) => onSetFilter('status', e.target.value)}
        className="w-40"
        aria-label="Filter by status"
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </Select>

      {hasActiveFilters && (
        <Button variant="ghost" size="sm" onClick={onClearAll} className="gap-1 text-muted-foreground">
          <X className="h-3.5 w-3.5" />
          Clear
        </Button>
      )}
    </div>
  )
}
