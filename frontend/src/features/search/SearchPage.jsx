import { useCallback, useState } from 'react'
import { Search, LayoutList, LayoutGrid, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useSearchState } from './useSearchState'
import { useEmployerSearch } from '@/shared/api/employers'
import { SearchBar } from './SearchBar'
import { SearchFilters } from './SearchFilters'
import { ResultsTable } from './ResultsTable'
import { SearchResultCard } from './SearchResultCard'
import { EmptyState } from './EmptyState'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'

const PAGE_SIZE = 25

export function SearchPage() {
  const { filters, page, hasActiveSearch, setFilter, clearFilter, clearAll, setPage } = useSearchState()

  const [viewMode, setViewMode] = useState(() => {
    try { return localStorage.getItem('search-view-mode') || 'table' } catch { return 'table' }
  })
  const handleViewModeChange = useCallback((mode) => {
    setViewMode(mode)
    try { localStorage.setItem('search-view-mode', mode) } catch {}
  }, [])

  const { data, isLoading, isError, error } = useEmployerSearch({
    name: filters.q || undefined,
    state: filters.state || undefined,
    naics: filters.naics || undefined,
    source_type: filters.source_type || undefined,
    has_union: filters.has_union || undefined,
    min_workers: filters.min_workers || undefined,
    max_workers: filters.max_workers || undefined,
    score_tier: filters.score_tier || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    enabled: hasActiveSearch,
  })

  const handleSearch = useCallback((query) => {
    setFilter('q', query)
  }, [setFilter])

  // Pre-search hero state
  if (!hasActiveSearch) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
        <div className="flex items-center gap-3 mb-4">
          <Search className="h-10 w-10 text-primary" />
          <h1 className="text-4xl font-bold tracking-tight">Employer Search</h1>
        </div>
        <p className="text-muted-foreground mb-8 text-center max-w-md">
          Search across {(107_025).toLocaleString()} employers from NLRB elections, LM filings, and more.
        </p>
        <div className="w-full max-w-xl">
          <SearchBar variant="hero" initialValue="" onSearch={handleSearch} />
        </div>
      </div>
    )
  }

  // Post-search state
  return (
    <div className="space-y-4">
      <div className="max-w-xl">
        <SearchBar variant="compact" initialValue={filters.q} onSearch={handleSearch} />
      </div>

      <HelpSection>
        <p><strong>Search bar:</strong> Search by employer name, city, or state. Results appear after you type at least 3 characters.</p>
        <p><strong>Advanced Filters:</strong> Click Filters to narrow results by state, industry (NAICS code), or data source.</p>
        <p><strong>Results table:</strong> Click any employer name to open their full profile. Click column headers to sort. Source badges show which government databases have records for each employer.</p>
      </HelpSection>

      <SearchFilters
        filters={filters}
        onSetFilter={setFilter}
        onClearFilter={clearFilter}
      />

      {isLoading && !data && <PageSkeleton variant="search" />}

      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive flex items-center justify-between">
          <span>Failed to load results: {error?.message || 'Unknown error'}</span>
          <Button variant="outline" size="sm" onClick={() => handleSearch(filters.q)}>
            Retry
          </Button>
        </div>
      )}

      {data && data.total === 0 && (
        <EmptyState query={filters.q} />
      )}

      {data && data.total > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {data.total.toLocaleString()} employer{data.total !== 1 ? 's' : ''} found
            </p>
            <div className="flex items-center border">
              <button
                type="button"
                onClick={() => handleViewModeChange('table')}
                className={cn('p-1.5', viewMode === 'table' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
                aria-label="Table view"
              >
                <LayoutList className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => handleViewModeChange('card')}
                className={cn('p-1.5', viewMode === 'card' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent')}
                aria-label="Card view"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
            </div>
          </div>

          {viewMode === 'table' ? (
            <ResultsTable
              data={data.employers}
              total={data.total}
              page={page}
              onPageChange={setPage}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.employers.map((emp) => (
                  <SearchResultCard key={emp.canonical_id} employer={emp} />
                ))}
              </div>
              {data.total > PAGE_SIZE && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    Showing {(page - 1) * PAGE_SIZE + 1}&ndash;{Math.min(page * PAGE_SIZE, data.total)} of {data.total.toLocaleString()}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                      <ChevronLeft className="h-4 w-4" /> Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">Page {page} of {Math.ceil(data.total / PAGE_SIZE)}</span>
                    <Button variant="outline" size="sm" disabled={page >= Math.ceil(data.total / PAGE_SIZE)} onClick={() => setPage(page + 1)}>
                      Next <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
