import { useCallback, useEffect, useState } from 'react'
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

  useEffect(() => { document.title = 'Search - The Organizer' }, [])

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
        <h1 className="font-editorial text-4xl font-bold tracking-tight mb-2">Employer Search</h1>
        <p className="text-muted-foreground mb-8 text-center max-w-md">
          Search across 100,000+ employers from NLRB elections, LM filings, and more.
        </p>
        <div className="w-full max-w-xl">
          <SearchBar variant="hero" initialValue="" onSearch={handleSearch} />
        </div>
        <div className="mt-10 flex gap-5 justify-center">
          {[
            { num: '107K+', label: 'Employers' },
            { num: '26K+', label: 'Unions' },
            { num: '6.8M+', label: 'Records' },
            { num: '18', label: 'Data Sources' },
          ].map(({ num, label }) => (
            <div key={label} className="text-center">
              <p className="font-editorial text-xl font-bold text-[#1a6b5a]">{num}</p>
              <p className="text-[11px] uppercase text-[#8a7e6d]">{label}</p>
            </div>
          ))}
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
        <p><strong>Search bar:</strong> Search by employer name, city, or state. Results appear after you type at least 3 characters. The search looks across all employer names in the database, including alternate names and former names.</p>
        <p><strong>Advanced Filters:</strong> Click to expand additional filters that narrow your results:</p>
        <ul className="list-disc pl-5 space-y-1 text-sm">
          <li><strong>State:</strong> Filter to employers in a specific state.</li>
          <li><strong>Industry:</strong> Filter by NAICS code. Start typing an industry name to see options.</li>
          <li><strong>Employee size:</strong> Filter to employers within a size range (e.g. 100-500).</li>
          <li><strong>Score tier:</strong> Show only employers in a specific tier (Priority, Strong, etc.).</li>
          <li><strong>Data sources:</strong> Show only employers with records in specific databases.</li>
          <li><strong>Union status:</strong> Show only employers with existing union contracts, or only those without.</li>
        </ul>
        <p><strong>Results table columns:</strong> Click any employer name to open their full profile. Click column headers to sort. The arrow indicates which column is currently sorted.</p>
        <p><strong>Table/Card toggle:</strong> Switch between a compact table view (more results visible) and a card view (more detail per result). Both show the same data.</p>
      </HelpSection>

      <SearchFilters
        filters={filters}
        onSetFilter={setFilter}
        onClearFilter={clearFilter}
      />

      {isLoading && !data && <PageSkeleton variant="search" />}

      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive flex items-center justify-between">
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
            <p className="text-sm" aria-live="polite">
              <strong>{data.total.toLocaleString()}</strong> result{data.total !== 1 ? 's' : ''} for &ldquo;{filters.q}&rdquo;
            </p>
            <div className="flex items-center rounded-md border overflow-hidden">
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
