import { useState } from 'react'
import { Users, SearchX, LayoutList, GitBranch } from 'lucide-react'
import { useUnionsState } from './useUnionsState'
import { useUnionSearch, useNationalUnions } from '@/shared/api/unions'
import { NationalUnionsSummary } from './NationalUnionsSummary'
import { UnionFilters } from './UnionFilters'
import { UnionResultsTable } from './UnionResultsTable'
import { AffiliationTree } from './AffiliationTree'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50

export function UnionsPage() {
  const { filters, page, hasActiveFilters, setFilter, clearFilter, clearAll, setPage } = useUnionsState()
  const [viewMode, setViewMode] = useState('list')

  const nationalQuery = useNationalUnions()

  const { data, isLoading, isError, error } = useUnionSearch({
    name: filters.q || undefined,
    aff_abbr: filters.aff_abbr || undefined,
    sector: filters.sector || undefined,
    state: filters.state || undefined,
    min_members: filters.min_members ? Number(filters.min_members) : undefined,
    has_employers: filters.has_employers ? filters.has_employers === 'true' : undefined,
    page,
    limit: PAGE_SIZE,
  })

  const handleAffiliationClick = (aff_abbr) => {
    setFilter('aff_abbr', aff_abbr)
  }

  const showTree = viewMode === 'tree' && !hasActiveFilters && !filters.q

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Users className="h-6 w-6 text-primary" />
        <h1 className="text-2xl font-bold">Union Explorer</h1>
      </div>

      <HelpSection>
        <p><strong>What this page is for:</strong> Browse and research unions, their organizational structure, and the employers they represent.</p>
        <p><strong>National unions overview:</strong> Top affiliations by membership. Click an affiliation chip to filter the table below.</p>
        <p><strong>Filters:</strong> Narrow results by affiliation, sector, state, minimum members, or whether the union has linked employers.</p>
        <p><strong>Union profiles:</strong> Click any union row to see detailed membership trends, financials, employers, and elections.</p>
      </HelpSection>

      <NationalUnionsSummary
        data={nationalQuery.data?.national_unions}
        isLoading={nationalQuery.isLoading}
        onAffiliationClick={handleAffiliationClick}
      />

      <div className="flex items-center gap-2">
        <div className="flex items-center border">
          <button
            type="button"
            onClick={() => setViewMode('list')}
            className={cn('px-3 py-1.5 text-sm', viewMode === 'list' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
          >
            <span className="flex items-center gap-1.5">
              <LayoutList className="h-3.5 w-3.5" />
              List View
            </span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('tree')}
            className={cn('px-3 py-1.5 text-sm', showTree ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
          >
            <span className="flex items-center gap-1.5">
              <GitBranch className="h-3.5 w-3.5" />
              Tree View
            </span>
          </button>
        </div>
        {showTree && (
          <span className="text-xs text-muted-foreground">Expand affiliations to browse by state and local</span>
        )}
      </div>

      {showTree ? (
        <AffiliationTree affiliations={nationalQuery.data?.national_unions} />
      ) : (
        <>
          <UnionFilters
            filters={filters}
            onSetFilter={setFilter}
            onClearFilter={clearFilter}
            onClearAll={clearAll}
          />

          {isLoading && !data && <PageSkeleton variant="unions" />}

          {isError && (
            <div className="border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
              Failed to load unions: {error?.message || 'Unknown error'}
            </div>
          )}

          {data && data.total === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-1">No unions found</h3>
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
                {data.total.toLocaleString()} union{data.total !== 1 ? 's' : ''} found
              </p>
              <UnionResultsTable
                data={data.unions}
                total={data.total}
                page={page}
                onPageChange={setPage}
              />
            </>
          )}
        </>
      )}
    </div>
  )
}
