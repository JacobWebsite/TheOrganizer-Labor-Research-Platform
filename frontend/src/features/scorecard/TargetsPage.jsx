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
      <div className="flex items-center gap-2">
        <Target className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Organizing Targets</h1>
      </div>

      <HelpSection>
        <p><strong>What this page is for:</strong> Employers ranked by their potential for a successful organizing campaign, based on available data signals.</p>
        <p><strong>Quality score:</strong> A data completeness indicator showing how many scoring factors have data for each employer. Higher quality = more reliable assessment.</p>
        <p><strong>Tier labels:</strong> Priority (top 3%) are highest-value targets. Strong (next 12%) are very promising. Promising (next 25%) have good potential. Moderate and Low have fewer signals.</p>
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
        <div className="border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load targets: {error?.message || 'Unknown error'}
        </div>
      )}

      {data && data.total === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-1">No targets found</h3>
          {hasActiveFilters && (
            <p className="text-muted-foreground mb-4">
              Try adjusting your filters or search term.
            </p>
          )}
        </div>
      )}

      {data && data.total > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
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
