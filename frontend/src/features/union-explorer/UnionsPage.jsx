import { useState, useEffect } from 'react'
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

  useEffect(() => { document.title = 'Union Explorer - The Organizer' }, [])

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-editorial text-3xl font-bold">Union Explorer</h1>
          {nationalQuery.data?.national_unions && (
            <p className="text-sm text-[#8a7e6d] mt-1">
              {nationalQuery.data.national_unions.reduce((s, u) => s + (u.local_count || 0), 0).toLocaleString()} organizations
              {' '}&middot;{' '}
              {nationalQuery.data.national_unions.reduce((s, u) => s + (u.total_members || 0), 0).toLocaleString()} members
            </p>
          )}
        </div>
        <div className="flex items-center rounded-md border overflow-hidden">
          <button
            type="button"
            onClick={() => setViewMode('list')}
            className={cn('px-3 py-1.5 text-sm', viewMode === 'list' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
          >
            <span className="flex items-center gap-1.5">
              <LayoutList className="h-3.5 w-3.5" />
              List
            </span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('tree')}
            className={cn('px-3 py-1.5 text-sm', showTree ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
          >
            <span className="flex items-center gap-1.5">
              <GitBranch className="h-3.5 w-3.5" />
              Tree
            </span>
          </button>
        </div>
      </div>

      <HelpSection>
        <p><strong>What this page is for:</strong> Browse and research unions, their organizational structure, and the employers they represent. Use the search bar to find a specific union, or browse the hierarchy tree to explore how unions are organized.</p>
        <p><strong>Hierarchy tree:</strong> Unions are organized in a parent-child structure. National and international unions are at the top, with regional bodies and local unions underneath. Click the arrow to expand any level.</p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>Affiliation (e.g. AFL-CIO, Change to Win):</strong> The largest groupings of unions.</li>
          <li><strong>International/National union (e.g. SEIU, IBEW):</strong> Individual unions that operate across the country.</li>
          <li><strong>Local union (e.g. SEIU Local 1199):</strong> The local chapter that directly represents workers at specific employers.</li>
        </ul>
        <p><strong>Union profile header:</strong> Abbreviation, affiliation, member count, number of employers, and number of local chapters.</p>
        <p><strong>Relationship map:</strong> The expandable list below the header shows the full organizational tree -- from the national union down through its locals and the specific employers each local represents. Click any employer name to open their employer profile.</p>
      </HelpSection>

      <NationalUnionsSummary
        data={nationalQuery.data?.national_unions}
        isLoading={nationalQuery.isLoading}
        onAffiliationClick={handleAffiliationClick}
      />

      {showTree && (
        <span className="text-xs text-muted-foreground">Expand affiliations to browse by state and local</span>
      )}

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
            <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
              Failed to load unions: {error?.message || 'Unknown error'}
            </div>
          )}

          {data && data.total === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="font-editorial text-lg font-semibold mb-1">No unions found</h3>
              {hasActiveFilters && (
                <p className="text-muted-foreground mb-4">
                  Try adjusting your filters or search term.
                </p>
              )}
            </div>
          )}

          {data && data.total > 0 && (
            <>
              <p className="font-editorial text-lg">
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
