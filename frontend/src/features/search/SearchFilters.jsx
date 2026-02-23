import { useState } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { useStates } from '@/shared/api/lookups'
import { useNaicsSectors } from '@/shared/api/lookups'

const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'F7', label: 'F7 (LM filings)' },
  { value: 'NLRB', label: 'NLRB (Elections)' },
  { value: 'VR', label: 'VR (Voluntary)' },
  { value: 'MANUAL', label: 'Manual' },
]

const UNION_STATUS_OPTIONS = [
  { value: '', label: 'Any union status' },
  { value: 'true', label: 'Has union' },
  { value: 'false', label: 'No union' },
]

/**
 * Filter panel with State, NAICS, and Source Type dropdowns + active filter chips.
 */
export function SearchFilters({ filters, onSetFilter, onClearFilter }) {
  const [expanded, setExpanded] = useState(
    Boolean(filters.state || filters.naics || filters.source_type || filters.has_union)
  )

  const { data: statesData } = useStates()
  const { data: naicsData } = useNaicsSectors()

  const states = statesData?.states || []
  const sectors = naicsData?.sectors || []

  const activeFilters = [
    filters.state && { key: 'state', label: `State: ${filters.state}` },
    filters.naics && { key: 'naics', label: `Industry: ${filters.naics}` },
    filters.source_type && { key: 'source_type', label: `Source: ${filters.source_type}` },
    filters.has_union && { key: 'has_union', label: filters.has_union === 'true' ? 'Has union' : 'No union' },
  ].filter(Boolean)

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setExpanded((v) => !v)}
          className="gap-1.5"
        >
          <SlidersHorizontal className="h-4 w-4" />
          Filters
          {activeFilters.length > 0 && (
            <span className="ml-1 inline-flex h-5 w-5 items-center justify-center bg-primary text-primary-foreground text-xs font-bold">
              {activeFilters.length}
            </span>
          )}
        </Button>

        {/* Active filter chips */}
        {activeFilters.map(({ key, label }) => (
          <span
            key={key}
            className="inline-flex items-center gap-1 border bg-secondary px-2 py-1 text-xs font-medium"
          >
            {label}
            <button
              type="button"
              onClick={() => onClearFilter(key)}
              className="ml-0.5 hover:text-destructive"
              aria-label={`Remove ${label} filter`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>

      {expanded && (
        <div className="flex flex-wrap gap-3">
          <Select
            value={filters.state}
            onChange={(e) => onSetFilter('state', e.target.value)}
            className="w-48"
            aria-label="Filter by state"
          >
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s.state} value={s.state}>
                {s.state} ({s.employer_count.toLocaleString()})
              </option>
            ))}
          </Select>

          <Select
            value={filters.naics}
            onChange={(e) => onSetFilter('naics', e.target.value)}
            className="w-64"
            aria-label="Filter by industry"
          >
            <option value="">All industries</option>
            {sectors.map((s) => (
              <option key={s.naics_2digit} value={s.naics_2digit}>
                {s.naics_2digit} &mdash; {s.sector_name}
              </option>
            ))}
          </Select>

          <Select
            value={filters.source_type}
            onChange={(e) => onSetFilter('source_type', e.target.value)}
            className="w-48"
            aria-label="Filter by source"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>

          <Select
            value={filters.has_union}
            onChange={(e) => onSetFilter('has_union', e.target.value)}
            className="w-48"
            aria-label="Filter by union status"
          >
            {UNION_STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>
      )}
    </div>
  )
}
