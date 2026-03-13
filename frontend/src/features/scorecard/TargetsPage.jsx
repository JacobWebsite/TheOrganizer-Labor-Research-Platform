import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Target, SearchX, Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTargetsState } from './useTargetsState'
import { useNonUnionTargets, useTargetStats, useTargetScorecardStats } from '@/shared/api/targets'
import { TargetStats } from './TargetStats'
import { TargetsFilters } from './TargetsFilters'
import { TargetsTable } from './TargetsTable'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'

const PAGE_SIZE = 50

const TIER_COLORS = {
  Priority: '#c23a22',
  Strong: '#1a6b5a',
  Promising: '#c78c4e',
  Moderate: '#8a7e6d',
  Low: '#d9cebb',
}

export function TargetsPage() {
  const navigate = useNavigate()
  const { filters, sort, order, page, hasActiveFilters, setFilter, clearFilter, clearAll, setSort, setPage } = useTargetsState()
  const [selectedIds, setSelectedIds] = useState([])

  useEffect(() => { document.title = 'Organizing Targets - The Organizer' }, [])

  const statsQuery = useTargetStats()
  const scorecardStatsQuery = useTargetScorecardStats()

  const { data, isLoading, isError, error } = useNonUnionTargets({
    q: filters.q || undefined,
    state: filters.state || undefined,
    naics: filters.naics || undefined,
    min_employees: filters.min_employees ? Number(filters.min_employees) : undefined,
    max_employees: filters.max_employees ? Number(filters.max_employees) : undefined,
    is_federal_contractor: filters.is_federal_contractor ? filters.is_federal_contractor === 'true' : undefined,
    is_nonprofit: filters.is_nonprofit ? filters.is_nonprofit === 'true' : undefined,
    has_enforcement: filters.has_enforcement ? filters.has_enforcement === 'true' : undefined,
    min_signals: filters.min_signals ? Number(filters.min_signals) : undefined,
    min_quality: filters.min_quality ? Number(filters.min_quality) : undefined,
    sort,
    order,
    page,
    limit: PAGE_SIZE,
  })

  function toggleSelected(id, checked) {
    setSelectedIds((prev) => {
      if (checked) {
        if (prev.includes(id) || prev.length >= 3) return prev
        return [...prev, id]
      }
      return prev.filter((candidate) => candidate !== id)
    })
  }

  function toggleSelectedPage(rows, checked) {
    const pageIds = rows.map((row) => `MASTER-${row.id}`)
    setSelectedIds((prev) => {
      if (!checked) {
        return prev.filter((id) => !pageIds.includes(id))
      }
      const next = [...prev]
      for (const id of pageIds) {
        if (next.includes(id)) continue
        if (next.length >= 3) break
        next.push(id)
      }
      return next
    })
  }

  function openCompare() {
    if (selectedIds.length < 2) return
    navigate(`/compare?ids=${selectedIds.join(',')}`)
  }

  return (
    <div className="space-y-4">
      <h1 className="font-editorial text-[32px] font-bold">Organizing Targets</h1>
      <p className="text-base text-[#2c2418]">
        <strong className="text-[#c23a22] text-xl">{statsQuery.data?.flags?.enforcement_true?.toLocaleString() || '---'}</strong>
        {' '}enforcement targets identified across{' '}
        {statsQuery.data?.total?.toLocaleString() || '---'} non-union employers
      </p>

      {/* Gold standard tier distribution bar */}
      {scorecardStatsQuery.data?.gold_standard_tiers && (() => {
        const tiers = scorecardStatsQuery.data.gold_standard_tiers
        const tierMap = {}
        tiers.forEach(t => { tierMap[t.tier] = t.count })
        const totalScored = scorecardStatsQuery.data.total_scored || 1
        const ordered = ['bronze', 'silver', 'gold', 'platinum']
        const tierColors = { bronze: '#8b5e3c', silver: '#6b6b6b', gold: '#c78c4e', platinum: '#6b5b8a', stub: '#d9cebb' }
        const nonStub = ordered.filter(t => tierMap[t])
        if (nonStub.length === 0) return null
        return (
          <div className="w-full h-8 rounded-md border border-[#d9cebb] flex overflow-hidden">
            {ordered.map((tier) => {
              const count = tierMap[tier] || 0
              const pct = (count / totalScored) * 100
              if (pct === 0) return null
              return (
                <div
                  key={tier}
                  className="flex items-center justify-center text-xs font-medium text-white overflow-hidden"
                  style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: tierColors[tier] }}
                  title={`${tier}: ${count.toLocaleString()}`}
                >
                  {pct > 8 && <span className="capitalize">{tier} {count.toLocaleString()}</span>}
                </div>
              )
            })}
            {tierMap['stub'] > 0 && (
              <div
                className="flex items-center justify-center text-xs font-medium text-[#2c2418] overflow-hidden flex-1"
                style={{ backgroundColor: '#d9cebb' }}
                title={`Unrated: ${tierMap['stub'].toLocaleString()}`}
              >
                <span>Unrated {tierMap['stub'].toLocaleString()}</span>
              </div>
            )}
          </div>
        )
      })()}

      {/* Top Priority targets */}
      {data && (() => {
        const priorityTargets = (data.results || []).filter(r => r.gold_standard_tier === 'bronze' || r.signals_present >= 4).slice(0, 5)
        if (priorityTargets.length === 0) return null
        return (
          <div>
            <h2 className="font-editorial text-lg mb-3">Top Priority Targets</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
              {priorityTargets.map((t) => (
                <div
                  key={t.id}
                  className="bg-[#faf6ef] border-l-4 border-l-[#c23a22] border border-[#d9cebb] rounded p-4 cursor-pointer hover:bg-[#f5f0e8] transition-colors"
                  onClick={() => navigate(`/employers/MASTER-${t.id}`)}
                >
                  <p className="font-medium text-sm truncate">{t.display_name}</p>
                  <p className="font-editorial text-lg font-bold text-[#c23a22] mt-1">{t.signals_present || 0}/9</p>
                  <p className="text-[11px] text-[#8a7e6d] mt-1 truncate">{t.industry || t.naics_description || '--'}</p>
                  {t.employee_count != null && (
                    <p className="text-[11px] text-[#8a7e6d]">{Number(t.employee_count).toLocaleString()} workers</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      <HelpSection>
        <p><strong>What this page is for:</strong> This page shows organizing targets -- employers ranked by their potential for a successful organizing campaign. These are employers where the available data suggests favorable conditions for workers to organize.</p>
        <p><strong>Tier summary cards:</strong> The cards at the top show how many employers fall into each tier. Click a tier card to filter the table below to only that tier.</p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>Priority (top 3%):</strong> Highest-value targets. Start here when planning campaigns.</li>
          <li><strong>Strong (next 12%):</strong> Very promising. Worth detailed assessment.</li>
          <li><strong>Promising (next 25%):</strong> Good potential. Investigate further.</li>
          <li><strong>Moderate (next 35%):</strong> Some signals. Keep on the radar.</li>
          <li><strong>Low (bottom 25%):</strong> Few signals in current data.</li>
        </ul>
        <p>Tier counts update whenever new data is loaded into the system. The same employer may shift tiers over time as new information becomes available.</p>
        <p><strong>Bulk actions:</strong> Select multiple employers using the checkboxes, then use the action bar to export CSV or flag all for follow-up.</p>
      </HelpSection>

      <TargetStats />

      <TargetsFilters
        filters={filters}
        sort={sort}
        onSetFilter={setFilter}
        onClearFilter={clearFilter}
        onClearAll={clearAll}
        onSetSort={setSort}
        currentResults={data?.results}
        totalCount={data?.total}
      />

      {isLoading && !data && <PageSkeleton variant="targets" />}

      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Failed to load targets: {error?.message || 'Unknown error'}
        </div>
      )}

      {data && data.total === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">No targets found</h3>
          {hasActiveFilters && (
            <p className="text-muted-foreground mb-4">
              Try adjusting your filters or search term.
            </p>
          )}
        </div>
      )}

      {data && data.total > 0 && (
        <>
          <p className="font-editorial text-lg" aria-live="polite">
            {data.total.toLocaleString()} target{data.total !== 1 ? 's' : ''} found
          </p>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3">
            <div className="text-sm text-muted-foreground">
              {selectedIds.length > 0
                ? `${selectedIds.length} employer${selectedIds.length !== 1 ? 's' : ''} selected for compare`
                : 'Select 2 to 3 employers to compare side by side.'}
            </div>
            <div className="flex items-center gap-2">
              {selectedIds.length > 0 && (
                <Button variant="ghost" size="sm" onClick={() => setSelectedIds([])}>
                  Clear
                </Button>
              )}
              <Button
                size="sm"
                className="gap-1.5"
                disabled={selectedIds.length < 2}
                onClick={openCompare}
              >
                <Scale className="h-4 w-4" />
                Compare Selected
              </Button>
            </div>
          </div>
          <TargetsTable
            data={data.results}
            total={data.total}
            page={data.page}
            pages={data.pages}
            onPageChange={setPage}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelected}
            onToggleSelectPage={toggleSelectedPage}
            maxSelected={3}
          />
        </>
      )}
    </div>
  )
}
