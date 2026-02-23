import { useState, useCallback, useRef, useEffect } from 'react'
import { SlidersHorizontal, X, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useStates } from '@/shared/api/lookups'
import { useUnionSectors, useUnionAffiliations } from '@/shared/api/unions'

const HAS_EMPLOYERS_OPTIONS = [
  { value: '', label: 'Any' },
  { value: 'true', label: 'Yes' },
  { value: 'false', label: 'No' },
]

const FILTER_LABELS = {
  q: 'Search',
  aff_abbr: 'Affiliation',
  sector: 'Sector',
  state: 'State',
  min_members: 'Min members',
  has_employers: 'Has employers',
}

/**
 * Filter bar for unions page: search + dropdowns + toggles + active chips.
 */
export function UnionFilters({ filters, onSetFilter, onClearFilter, onClearAll }) {
  const [expanded, setExpanded] = useState(
    Boolean(filters.aff_abbr || filters.sector || filters.state ||
            filters.min_members || filters.has_employers)
  )

  const { data: statesData } = useStates()
  const { data: sectorsData } = useUnionSectors()
  const { data: affiliationsData } = useUnionAffiliations()

  const states = statesData?.states || []
  const sectors = Array.isArray(sectorsData) ? sectorsData : (sectorsData?.sectors || [])
  const affiliations = Array.isArray(affiliationsData) ? affiliationsData : (affiliationsData?.affiliations || [])

  // Debounced search
  const [searchValue, setSearchValue] = useState(filters.q)
  const timerRef = useRef(null)

  useEffect(() => {
    setSearchValue(filters.q)
  }, [filters.q])

  const handleSearchChange = useCallback((e) => {
    const v = e.target.value
    setSearchValue(v)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      onSetFilter('q', v)
    }, 300)
  }, [onSetFilter])

  // Active filter chips
  const activeFilters = [
    filters.q && { key: 'q', label: `Search: ${filters.q}` },
    filters.aff_abbr && { key: 'aff_abbr', label: `Affiliation: ${filters.aff_abbr}` },
    filters.sector && { key: 'sector', label: `Sector: ${filters.sector}` },
    filters.state && { key: 'state', label: `State: ${filters.state}` },
    filters.min_members && { key: 'min_members', label: `Min members: ${filters.min_members}` },
    filters.has_employers && { key: 'has_employers', label: `Has employers: ${filters.has_employers === 'true' ? 'Yes' : 'No'}` },
  ].filter(Boolean)

  return (
    <div className="space-y-2">
      {/* Search + filter toggle row */}
      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchValue}
            onChange={handleSearchChange}
            placeholder="Search unions..."
            className="pl-9 h-9"
          />
        </div>

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

        {activeFilters.length > 0 && (
          <Button variant="ghost" size="sm" onClick={onClearAll} className="text-xs">
            Clear all
          </Button>
        )}
      </div>

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
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
                aria-label={`Remove ${FILTER_LABELS[key] || key} filter`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Expanded filter controls */}
      {expanded && (
        <div className="flex flex-wrap gap-3 border-t pt-3">
          <Select
            value={filters.sector}
            onChange={(e) => onSetFilter('sector', e.target.value)}
            className="w-48"
            aria-label="Filter by sector"
          >
            <option value="">All sectors</option>
            {sectors.map((s) => (
              <option key={s.sector_code || s.sector} value={s.sector_code || s.sector}>
                {s.sector_name || s.sector_code || s.sector} ({(s.union_count || s.count || 0).toLocaleString()})
              </option>
            ))}
          </Select>

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
            value={filters.aff_abbr}
            onChange={(e) => onSetFilter('aff_abbr', e.target.value)}
            className="w-64"
            aria-label="Filter by affiliation"
          >
            <option value="">All affiliations</option>
            {affiliations.map((a) => (
              <option key={a.aff_abbr} value={a.aff_abbr}>
                {a.aff_abbr} ({(a.local_count || 0).toLocaleString()} locals)
              </option>
            ))}
          </Select>

          <Input
            type="number"
            value={filters.min_members}
            onChange={(e) => onSetFilter('min_members', e.target.value)}
            placeholder="Min members"
            className="w-36 h-9"
            min={0}
          />

          <Select
            value={filters.has_employers}
            onChange={(e) => onSetFilter('has_employers', e.target.value)}
            className="w-44"
            aria-label="Has employers"
          >
            <option value="">Employers: Any</option>
            {HAS_EMPLOYERS_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>Employers: {o.label}</option>
            ))}
          </Select>
        </div>
      )}
    </div>
  )
}
