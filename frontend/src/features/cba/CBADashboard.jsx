import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { SearchX, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCBADocuments, useCBACategories } from '@/shared/api/cba'
import { PageSkeleton } from '@/shared/components/PageSkeleton'

const PAGE_SIZE = 25

export function CBADashboard() {
  useEffect(() => { document.title = 'Contracts - The Organizer' }, [])

  const [filters, setFilters] = useState({ employer: '', union: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, error } = useCBADocuments({
    employer: filters.employer || undefined,
    union: filters.union || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    page,
    limit: PAGE_SIZE,
  })

  const categoriesQuery = useCBACategories()

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setPage(1)
  }

  const stats = data?.stats || {}
  const documents = data?.results || []
  const totalPages = stats.total_contracts ? Math.ceil(stats.total_contracts / PAGE_SIZE) : 0
  const categories = categoriesQuery.data?.results || []

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-editorial text-3xl font-bold">Contracts</h1>
          {stats.total_contracts != null && (
            <p className="text-sm text-[#8a7e6d] mt-1">
              {stats.total_contracts.toLocaleString()} collective bargaining agreements
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Link to="/cbas/search" className="rounded px-3 py-1.5 text-sm font-medium border hover:bg-muted/30 transition-colors">Search</Link>
          <Link to="/cbas/compare" className="rounded px-3 py-1.5 text-sm font-medium border hover:bg-muted/30 transition-colors">Compare</Link>
          <Link to="/cbas/review" className="rounded px-3 py-1.5 text-sm font-medium border hover:bg-muted/30 transition-colors" style={{ backgroundColor: '#c78c4e', color: '#faf6ef', borderColor: '#c78c4e' }}>Rule Review</Link>
        </div>
      </div>

      {/* Stats cards */}
      {(stats.total_contracts != null || stats.total_provisions != null) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="border rounded-lg p-4">
            <p className="text-sm text-[#8a7e6d]">Total Contracts</p>
            <p className="text-2xl font-bold font-editorial">{(stats.total_contracts || 0).toLocaleString()}</p>
          </div>
          <div className="border rounded-lg p-4">
            <p className="text-sm text-[#8a7e6d]">Total Provisions</p>
            <p className="text-2xl font-bold font-editorial">{(stats.total_provisions || 0).toLocaleString()}</p>
          </div>
          <div className="border rounded-lg p-4">
            <p className="text-sm text-[#8a7e6d]">Categories</p>
            <p className="text-2xl font-bold font-editorial">{categories.length}</p>
          </div>
        </div>
      )}

      {/* Category breakdown */}
      {categories.length > 0 && (
        <div className="border rounded-lg p-4">
          <h2 className="font-editorial text-lg font-semibold mb-3">Category Breakdown</h2>
          <div className="flex flex-wrap gap-2">
            {categories.map(cat => (
              <span
                key={cat.category_name}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm"
              >
                {cat.display_name || cat.category_name}
                <span className="text-xs text-[#8a7e6d]">({cat.count})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Filter by employer..."
          value={filters.employer}
          onChange={e => handleFilterChange('employer', e.target.value)}
          className="rounded border px-3 py-1.5 text-sm bg-transparent"
        />
        <input
          type="text"
          placeholder="Filter by union..."
          value={filters.union}
          onChange={e => handleFilterChange('union', e.target.value)}
          className="rounded border px-3 py-1.5 text-sm bg-transparent"
        />
        <input
          type="date"
          value={filters.date_from}
          onChange={e => handleFilterChange('date_from', e.target.value)}
          className="rounded border px-3 py-1.5 text-sm bg-transparent"
          title="From date"
        />
        <input
          type="date"
          value={filters.date_to}
          onChange={e => handleFilterChange('date_to', e.target.value)}
          className="rounded border px-3 py-1.5 text-sm bg-transparent"
          title="To date"
        />
        {(filters.employer || filters.union || filters.date_from || filters.date_to) && (
          <button
            type="button"
            onClick={() => { setFilters({ employer: '', union: '', date_from: '', date_to: '' }); setPage(1) }}
            className="text-sm text-[#c78c4e] hover:underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Loading */}
      {isLoading && !data && <PageSkeleton />}

      {/* Error */}
      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Failed to load contracts: {error?.message || 'Unknown error'}
        </div>
      )}

      {/* Empty state */}
      {data && documents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">No contracts found</h3>
          <p className="text-muted-foreground">Try adjusting your filters.</p>
        </div>
      )}

      {/* Results table */}
      {documents.length > 0 && (
        <>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30">
                  <th className="text-left px-4 py-2 font-medium">Employer</th>
                  <th className="text-left px-4 py-2 font-medium">Union</th>
                  <th className="text-left px-4 py-2 font-medium">Effective</th>
                  <th className="text-left px-4 py-2 font-medium">Expiration</th>
                  <th className="text-right px-4 py-2 font-medium">Pages</th>
                  <th className="text-right px-4 py-2 font-medium">Articles</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr key={doc.cba_id} className="border-b last:border-b-0 hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-2">
                      <Link to={`/cbas/${doc.cba_id}/articles`} className="text-[#c78c4e] hover:underline font-medium">
                        {doc.employer_name_raw || 'Unknown employer'}
                      </Link>
                    </td>
                    <td className="px-4 py-2">{doc.union_name_raw || '-'}</td>
                    <td className="px-4 py-2">{doc.effective_date || '-'}</td>
                    <td className="px-4 py-2">{doc.expiration_date || '-'}</td>
                    <td className="px-4 py-2 text-right">{doc.page_count ?? '-'}</td>
                    <td className="px-4 py-2 text-right">
                      {doc.article_count > 0 ? doc.article_count : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#8a7e6d]">
                Page {page} of {totalPages}
              </p>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-1.5 rounded border disabled:opacity-30 hover:bg-muted/30"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded border disabled:opacity-30 hover:bg-muted/30"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
