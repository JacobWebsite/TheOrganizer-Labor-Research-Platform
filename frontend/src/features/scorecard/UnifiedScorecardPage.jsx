import { useState, useEffect } from 'react'
import { SearchX } from 'lucide-react'
import { useUnifiedScorecard, useUnifiedScorecardStats, useUnifiedScorecardStates } from '@/shared/api/scorecard'
import { UnifiedScorecardTable } from './UnifiedScorecardTable'
import { PageSkeleton } from '@/shared/components/PageSkeleton'

const PAGE_SIZE = 50

const TIER_COLORS = {
  Priority: '#c23a22',
  Strong: '#1a6b5a',
  Promising: '#c78c4e',
  Moderate: '#8a7e6b',
  Low: '#d9cebb',
}

const TIER_ORDER = ['Priority', 'Strong', 'Promising', 'Moderate', 'Low']

const SORT_OPTIONS = [
  { value: 'score', label: 'Score (High to Low)' },
  { value: 'factors', label: 'Factors Available' },
  { value: 'name', label: 'Employer Name' },
]

export function UnifiedScorecardPage() {
  useEffect(() => { document.title = 'Union Reference Scorecard - The Organizer' }, [])

  // Filter state
  const [state, setState] = useState('')
  const [scoreTier, setScoreTier] = useState('')
  const [minFactors, setMinFactors] = useState('')
  const [hasOsha, setHasOsha] = useState(null)
  const [hasNlrb, setHasNlrb] = useState(null)
  const [hasResearch, setHasResearch] = useState(null)
  const [hasCompound, setHasCompound] = useState(null)
  const [sort, setSort] = useState('score')
  const [offset, setOffset] = useState(0)

  // Reset offset when filters change
  function updateFilter(setter) {
    return (val) => {
      setter(val)
      setOffset(0)
    }
  }

  const statsQuery = useUnifiedScorecardStats()
  const statesQuery = useUnifiedScorecardStates()

  const { data, isLoading, isError, error } = useUnifiedScorecard({
    state: state || undefined,
    score_tier: scoreTier || undefined,
    min_factors: minFactors ? Number(minFactors) : undefined,
    has_osha: hasOsha,
    has_nlrb: hasNlrb,
    has_research: hasResearch,
    has_compound_enforcement: hasCompound,
    sort,
    offset,
    page_size: PAGE_SIZE,
  })

  const overview = statsQuery.data?.overview
  const tierDist = statsQuery.data?.tier_distribution

  // Build tier distribution bar data
  const tierBarData = tierDist
    ? TIER_ORDER.map((t) => {
        const found = tierDist.find((d) => d.score_tier === t)
        return { tier: t, count: found ? found.cnt : 0 }
      }).filter((d) => d.count > 0)
    : []
  const totalTierCount = tierBarData.reduce((sum, d) => sum + d.count, 0) || 1

  const hasActiveFilters = state || scoreTier || minFactors || hasOsha != null || hasNlrb != null || hasResearch != null || hasCompound != null

  function clearAll() {
    setState('')
    setScoreTier('')
    setMinFactors('')
    setHasOsha(null)
    setHasNlrb(null)
    setHasResearch(null)
    setHasCompound(null)
    setSort('score')
    setOffset(0)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <h1 className="font-editorial text-[32px] font-bold">Union Reference Scorecard</h1>
      <p className="text-base text-[#2c2418]">
        <strong className="text-[#c23a22] text-xl">{overview?.total_employers?.toLocaleString() || '---'}</strong>
        {' '}union reference employers scored across{' '}
        <strong>{overview?.avg_factors != null ? Number(overview.avg_factors).toFixed(1) : '---'}</strong>
        {' '}avg factors | avg score{' '}
        <strong>{overview?.avg_score != null ? Number(overview.avg_score).toFixed(1) : '---'}</strong>
      </p>

      {/* Tier distribution bar */}
      {tierBarData.length > 0 && (
        <div className="w-full h-8 rounded-md border border-[#d9cebb] flex overflow-hidden">
          {tierBarData.map(({ tier, count }) => {
            const pct = (count / totalTierCount) * 100
            const color = TIER_COLORS[tier]
            const isLight = tier === 'Low'
            return (
              <div
                key={tier}
                className="flex items-center justify-center text-xs font-medium overflow-hidden cursor-pointer"
                style={{
                  width: `${Math.max(pct, 2)}%`,
                  backgroundColor: color,
                  color: isLight ? '#2c2418' : '#faf6ef',
                }}
                title={`${tier}: ${count.toLocaleString()}`}
                onClick={() => { updateFilter(setScoreTier)(scoreTier === tier ? '' : tier) }}
              >
                {pct > 8 && <span>{tier} {count.toLocaleString()}</span>}
              </div>
            )
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 p-3 bg-[#faf6ef] border border-[#d9cebb] rounded-lg">
        {/* State dropdown */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">State</label>
          <select
            value={state}
            onChange={(e) => updateFilter(setState)(e.target.value)}
            className="h-8 rounded border border-[#d9cebb] bg-white px-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#c78c4e]"
          >
            <option value="">All States</option>
            {(statesQuery.data || []).map((s) => (
              <option key={s.state} value={s.state}>{s.state} ({s.count})</option>
            ))}
          </select>
        </div>

        {/* Tier dropdown */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">Tier</label>
          <select
            value={scoreTier}
            onChange={(e) => updateFilter(setScoreTier)(e.target.value)}
            className="h-8 rounded border border-[#d9cebb] bg-white px-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#c78c4e]"
          >
            <option value="">All Tiers</option>
            {TIER_ORDER.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {/* Min factors */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">Min Factors</label>
          <select
            value={minFactors}
            onChange={(e) => updateFilter(setMinFactors)(e.target.value)}
            className="h-8 rounded border border-[#d9cebb] bg-white px-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#c78c4e]"
          >
            <option value="">Any</option>
            {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={String(n)}>{n}+</option>
            ))}
          </select>
        </div>

        {/* Toggle: OSHA */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">OSHA</label>
          <button
            type="button"
            onClick={() => updateFilter(setHasOsha)(hasOsha === true ? null : true)}
            className={`h-8 rounded border px-3 text-xs font-medium transition-colors ${
              hasOsha === true
                ? 'bg-[#c23a22] text-white border-[#c23a22]'
                : 'bg-white text-[#2c2418] border-[#d9cebb] hover:border-[#c78c4e]'
            }`}
          >
            Has OSHA
          </button>
        </div>

        {/* Toggle: NLRB */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">NLRB</label>
          <button
            type="button"
            onClick={() => updateFilter(setHasNlrb)(hasNlrb === true ? null : true)}
            className={`h-8 rounded border px-3 text-xs font-medium transition-colors ${
              hasNlrb === true
                ? 'bg-[#1a6b5a] text-white border-[#1a6b5a]'
                : 'bg-white text-[#2c2418] border-[#d9cebb] hover:border-[#c78c4e]'
            }`}
          >
            Has NLRB
          </button>
        </div>

        {/* Toggle: Research */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">Research</label>
          <button
            type="button"
            onClick={() => updateFilter(setHasResearch)(hasResearch === true ? null : true)}
            className={`h-8 rounded border px-3 text-xs font-medium transition-colors ${
              hasResearch === true
                ? 'bg-[#c78c4e] text-white border-[#c78c4e]'
                : 'bg-white text-[#2c2418] border-[#d9cebb] hover:border-[#c78c4e]'
            }`}
          >
            Has Research
          </button>
        </div>

        {/* Toggle: Compound Enforcement */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">Compound</label>
          <button
            type="button"
            onClick={() => updateFilter(setHasCompound)(hasCompound === true ? null : true)}
            className={`h-8 rounded border px-3 text-xs font-medium transition-colors ${
              hasCompound === true
                ? 'bg-[#c23a22] text-white border-[#c23a22]'
                : 'bg-white text-[#2c2418] border-[#d9cebb] hover:border-[#c78c4e]'
            }`}
          >
            Compound Enf.
          </button>
        </div>

        {/* Sort */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[#8a7e6b]">Sort</label>
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setOffset(0) }}
            className="h-8 rounded border border-[#d9cebb] bg-white px-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#c78c4e]"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Clear all */}
        {hasActiveFilters && (
          <div className="flex flex-col gap-1 justify-end">
            <label className="text-[10px] font-medium uppercase tracking-wider text-transparent">Clear</label>
            <button
              type="button"
              onClick={clearAll}
              className="h-8 rounded border border-[#d9cebb] bg-white px-3 text-xs font-medium text-[#c23a22] hover:bg-[#c23a22]/5 transition-colors"
            >
              Clear All
            </button>
          </div>
        )}
      </div>

      {/* Loading */}
      {isLoading && !data && <PageSkeleton variant="targets" />}

      {/* Error */}
      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Failed to load scorecard: {error?.message || 'Unknown error'}
        </div>
      )}

      {/* Empty state */}
      {data && data.total === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">No employers found</h3>
          {hasActiveFilters && (
            <p className="text-muted-foreground mb-4">
              Try adjusting your filters.
            </p>
          )}
        </div>
      )}

      {/* Results */}
      {data && data.total > 0 && (
        <>
          <p className="font-editorial text-lg" aria-live="polite">
            {data.total.toLocaleString()} employer{data.total !== 1 ? 's' : ''} found
          </p>
          <UnifiedScorecardTable
            data={data.data}
            total={data.total}
            offset={data.offset}
            pageSize={data.page_size}
            onPageChange={setOffset}
          />
        </>
      )}
    </div>
  )
}
