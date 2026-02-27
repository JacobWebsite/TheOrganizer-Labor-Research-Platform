import { useEffect } from 'react'
import { Target, SearchX } from 'lucide-react'
import { useTargetsState } from './useTargetsState'
import { useNonUnionTargets } from '@/shared/api/targets'
import { TargetStats } from './TargetStats'
import { TargetsFilters } from './TargetsFilters'
import { TargetsTable } from './TargetsTable'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'

const PAGE_SIZE = 50

export function TargetsPage() {
  const { filters, sort, order, page, hasActiveFilters, setFilter, clearFilter, clearAll, setSort, setPage } = useTargetsState()

  useEffect(() => { document.title = 'Organizing Targets - The Organizer' }, [])

  const { data, isLoading, isError, error } = useNonUnionTargets({
    q: filters.q || undefined,
    state: filters.state || undefined,
    naics: filters.naics || undefined,
    min_employees: filters.min_employees ? Number(filters.min_employees) : undefined,
    max_employees: filters.max_employees ? Number(filters.max_employees) : undefined,
    is_federal_contractor: filters.is_federal_contractor ? filters.is_federal_contractor === 'true' : undefined,
    is_nonprofit: filters.is_nonprofit ? filters.is_nonprofit === 'true' : undefined,
    min_quality: filters.min_quality ? Number(filters.min_quality) : undefined,
    sort,
    order,
    page,
    limit: PAGE_SIZE,
  })

  return (
    <div className="space-y-4">
      <h1 className="font-editorial text-3xl font-bold">Organizing Targets</h1>

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
          <TargetsTable
            data={data.results}
            total={data.total}
            page={data.page}
            pages={data.pages}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  )
}
