import { useState, useCallback, useRef, useEffect } from 'react'
import { SlidersHorizontal, X, Search, Download, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useStates } from '@/shared/api/lookups'
import { useNaicsSectors } from '@/shared/api/lookups'

const SORT_OPTIONS = [
  { value: 'quality', label: 'Quality (highest)' },
  { value: 'employees', label: 'Employees (largest)' },
  { value: 'name', label: 'Name (A-Z)' },
  { value: 'signals', label: 'Signals (most)' },
  { value: 'enforcement', label: 'Enforcement (most)' },
]

const PRESET_FILTERS = [
  {
    label: 'Enforcement-flagged',
    icon: '!',
    filters: { has_enforcement: 'true', min_signals: '2' },
    description: 'Employers with OSHA/WHD/NLRB violations + 2+ signals',
  },
  {
    label: 'Large employers',
    icon: null,
    filters: { min_employees: '500', min_quality: '50' },
    description: '500+ employees, quality 50+',
  },
  {
    label: 'Fed contractors',
    icon: null,
    filters: { is_federal_contractor: 'true', min_signals: '2' },
    description: 'Government contractors with 2+ signals',
  },
  {
    label: 'Nonprofits',
    icon: null,
    filters: { is_nonprofit: 'true', min_signals: '2' },
    description: 'Nonprofit employers with 2+ signals',
  },
]

const BOOL_OPTIONS = [
  { value: '', label: 'Any' },
  { value: 'true', label: 'Yes' },
  { value: 'false', label: 'No' },
]

const FILTER_LABELS = {
  q: 'Search',
  state: 'State',
  naics: 'Industry',
  min_employees: 'Min employees',
  max_employees: 'Max employees',
  is_federal_contractor: 'Fed contractor',
  is_nonprofit: 'Nonprofit',
  min_quality: 'Min quality',
  has_enforcement: 'Has enforcement',
  min_signals: 'Min signals',
}

function exportCSV(rows) {
  const cols = [
    'display_name', 'city', 'state', 'naics', 'employee_count',
    'source_origin', 'signals_present', 'has_enforcement',
    'signal_osha', 'signal_whd', 'signal_nlrb',
    'signal_contracts', 'signal_financial', 'signal_industry_growth',
    'signal_union_density', 'gold_standard_tier',
    'is_federal_contractor', 'is_nonprofit',
  ]
  const header = cols.join(',')
  const csvRows = rows.map(r =>
    cols.map(c => {
      const v = r[c]
      if (v == null) return ''
      const s = String(v)
      return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s
    }).join(',')
  )
  const csv = [header, ...csvRows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `organizing_targets_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Filter bar for targets page: search + dropdowns + toggles + active chips.
 */
export function TargetsFilters({ filters, sort, onSetFilter, onClearFilter, onClearAll, onSetSort, currentResults, totalCount }) {
  const [expanded, setExpanded] = useState(
    Boolean(filters.state || filters.naics || filters.min_employees || filters.max_employees ||
            filters.is_federal_contractor || filters.is_nonprofit || filters.min_quality)
  )

  const { data: statesData } = useStates()
  const { data: naicsData } = useNaicsSectors()

  const states = statesData?.states || []
  const sectors = naicsData?.sectors || []

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
    filters.state && { key: 'state', label: `State: ${filters.state}` },
    filters.naics && { key: 'naics', label: `Industry: ${filters.naics}` },
    filters.min_employees && { key: 'min_employees', label: `Min employees: ${filters.min_employees}` },
    filters.max_employees && { key: 'max_employees', label: `Max employees: ${filters.max_employees}` },
    filters.is_federal_contractor && { key: 'is_federal_contractor', label: `Fed contractor: ${filters.is_federal_contractor === 'true' ? 'Yes' : 'No'}` },
    filters.is_nonprofit && { key: 'is_nonprofit', label: `Nonprofit: ${filters.is_nonprofit === 'true' ? 'Yes' : 'No'}` },
    filters.min_quality && { key: 'min_quality', label: `Min quality: ${filters.min_quality}` },
    filters.has_enforcement && { key: 'has_enforcement', label: `Enforcement: ${filters.has_enforcement === 'true' ? 'Yes' : 'No'}` },
    filters.min_signals && { key: 'min_signals', label: `Min signals: ${filters.min_signals}` },
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
            placeholder="Search employers..."
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

        <Select
          value={sort}
          onChange={(e) => onSetSort(e.target.value)}
          className="w-44"
          aria-label="Sort by"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </Select>

        {activeFilters.length > 0 && (
          <Button variant="ghost" size="sm" onClick={onClearAll} className="text-xs">
            Clear all
          </Button>
        )}

        {currentResults && currentResults.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportCSV(currentResults)}
            className="gap-1.5 ml-auto"
          >
            <Download className="h-4 w-4" />
            CSV
          </Button>
        )}
      </div>

      {/* Preset filter combos */}
      <div className="flex flex-wrap gap-1.5">
        {PRESET_FILTERS.map((preset) => (
          <Button
            key={preset.label}
            variant="outline"
            size="sm"
            className="text-xs gap-1"
            title={preset.description}
            onClick={() => {
              onClearAll()
              Object.entries(preset.filters).forEach(([k, v]) => onSetFilter(k, v))
            }}
          >
            <Zap className="h-3 w-3" />
            {preset.label}
          </Button>
        ))}
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

          <Input
            type="number"
            value={filters.min_employees}
            onChange={(e) => onSetFilter('min_employees', e.target.value)}
            placeholder="Min employees"
            className="w-36 h-9"
            min={0}
          />

          <Input
            type="number"
            value={filters.max_employees}
            onChange={(e) => onSetFilter('max_employees', e.target.value)}
            placeholder="Max employees"
            className="w-36 h-9"
            min={0}
          />

          <Select
            value={filters.is_federal_contractor}
            onChange={(e) => onSetFilter('is_federal_contractor', e.target.value)}
            className="w-40"
            aria-label="Federal contractor"
          >
            <option value="">Contractor: Any</option>
            {BOOL_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>Contractor: {o.label}</option>
            ))}
          </Select>

          <Select
            value={filters.is_nonprofit}
            onChange={(e) => onSetFilter('is_nonprofit', e.target.value)}
            className="w-40"
            aria-label="Nonprofit"
          >
            <option value="">Nonprofit: Any</option>
            {BOOL_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>Nonprofit: {o.label}</option>
            ))}
          </Select>

          <Input
            type="number"
            value={filters.min_quality}
            onChange={(e) => onSetFilter('min_quality', e.target.value)}
            placeholder="Min quality (0-100)"
            className="w-44 h-9"
            min={0}
            max={100}
          />

          <Select
            value={filters.has_enforcement}
            onChange={(e) => onSetFilter('has_enforcement', e.target.value)}
            className="w-40"
            aria-label="Has enforcement"
          >
            <option value="">Enforcement: Any</option>
            {BOOL_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>Enforcement: {o.label}</option>
            ))}
          </Select>

          <Input
            type="number"
            value={filters.min_signals}
            onChange={(e) => onSetFilter('min_signals', e.target.value)}
            placeholder="Min signals (0-8)"
            className="w-40 h-9"
            min={0}
            max={8}
          />
        </div>
      )}
    </div>
  )
}
