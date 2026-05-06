import { useState } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

const TIER_OPTIONS = [
  { value: '', label: 'All tiers' },
  { value: 'Priority', label: 'Priority' },
  { value: 'Strong', label: 'Strong' },
  { value: 'Promising', label: 'Promising' },
  { value: 'Moderate', label: 'Moderate' },
  { value: 'Low', label: 'Low' },
  // Speculative (added 2026-05-06): high modeled score but no direct
  // enforcement signals — formerly the silent half of "Promising"
  // that gave that tier a misleading 9.8% enforcement rate.
  { value: 'Speculative', label: 'Speculative (modeled, unverified)' },
]

/**
 * Filter panel with State, NAICS, and Source Type dropdowns + active filter chips.
 */
export function SearchFilters({ filters, onSetFilter, onClearFilter }) {
  const [expanded, setExpanded] = useState(
    Boolean(filters.state || filters.naics || filters.source_type || filters.has_union || filters.score_tier || filters.min_workers || filters.max_workers)
  )

  const { data: statesData } = useStates()
  const { data: naicsData } = useNaicsSectors()

  const states = statesData?.states || []
  const sectors = naicsData?.sectors || []

  const workersLabel = (() => {
    const min = filters.min_workers
    const max = filters.max_workers
    if (min && max) return `Workers: ${min}-${max}`
    if (min) return `Workers: ${min}+`
    if (max) return `Workers: \u2264${max}`
    return null
  })()

  const activeFilters = [
    filters.state && { key: 'state', label: `State: ${filters.state}` },
    filters.naics && { key: 'naics', label: `Industry: ${filters.naics}` },
    filters.source_type && { key: 'source_type', label: `Source: ${filters.source_type}` },
    filters.has_union && { key: 'has_union', label: filters.has_union === 'true' ? 'Has union' : 'No union' },
    filters.score_tier && { key: 'score_tier', label: `Tier: ${filters.score_tier}` },
    workersLabel && { key: 'workers', label: workersLabel },
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
              onClick={() => {
                if (key === 'workers') {
                  onClearFilter('min_workers')
                  onClearFilter('max_workers')
                } else {
                  onClearFilter(key)
                }
              }}
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

          <Select
            value={filters.score_tier}
            onChange={(e) => onSetFilter('score_tier', e.target.value)}
            className="w-48"
            aria-label="Filter by tier"
          >
            {TIER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>

          <div className="flex items-center gap-1">
            <div className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Min workers</span>
              <Input
                type="number"
                min="0"
                value={filters.min_workers}
                onChange={(e) => onSetFilter('min_workers', e.target.value)}
                className="w-28 h-10"
                placeholder="0"
                aria-label="Minimum workers"
              />
            </div>
            <span className="mt-4 text-muted-foreground">-</span>
            <div className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Max workers</span>
              <Input
                type="number"
                min="0"
                value={filters.max_workers}
                onChange={(e) => onSetFilter('max_workers', e.target.value)}
                className="w-28 h-10"
                placeholder="Any"
                aria-label="Maximum workers"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
