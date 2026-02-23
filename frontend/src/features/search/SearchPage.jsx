import { useCallback } from 'react'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSearchState } from './useSearchState'
import { useEmployerSearch } from '@/shared/api/employers'
import { SearchBar } from './SearchBar'
import { SearchFilters } from './SearchFilters'
import { ResultsTable } from './ResultsTable'
import { EmptyState } from './EmptyState'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { HelpSection } from '@/shared/components/HelpSection'

const PAGE_SIZE = 25

export function SearchPage() {
  const { filters, page, hasActiveSearch, setFilter, clearFilter, clearAll, setPage } = useSearchState()

  const { data, isLoading, isError, error } = useEmployerSearch({
    name: filters.q || undefined,
    state: filters.state || undefined,
    naics: filters.naics || undefined,
    source_type: filters.source_type || undefined,
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
          <p className="text-sm text-muted-foreground">
            {data.total.toLocaleString()} employer{data.total !== 1 ? 's' : ''} found
          </p>
          <ResultsTable
            data={data.employers}
            total={data.total}
            page={page}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  )
}
