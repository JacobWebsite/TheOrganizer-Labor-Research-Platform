import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, SearchX, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, X, Filter } from 'lucide-react'
import { useCBAProvisionSearch, useCBACategories, useCBAProvisionClasses, useCBAFilterOptions } from '@/shared/api/cba'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 25

function highlightMatch(text, query) {
  if (!text || !query) return text
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-[#c78c4e]/20 text-inherit rounded px-0.5">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const color = pct >= 80 ? 'bg-green-100 text-green-800'
    : pct >= 50 ? 'bg-yellow-100 text-yellow-800'
    : 'bg-red-100 text-red-800'
  return <span className={cn('text-xs px-1.5 py-0.5 rounded', color)}>{pct}%</span>
}

function ProvisionCard({ provision, query }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="px-4 py-3 border-b last:border-b-0">
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          className="mt-0.5 shrink-0 text-[#8a7e6d] hover:text-foreground"
        >
          {expanded
            ? <ChevronDown className="h-4 w-4" />
            : <ChevronUp className="h-4 w-4 rotate-180" />
          }
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {provision.category && (
              <span className="text-xs rounded-full border px-2 py-0.5 font-medium">{provision.category}</span>
            )}
            {provision.provision_class && provision.provision_class !== provision.category && (
              <span className="text-xs text-[#8a7e6d]">{provision.provision_class}</span>
            )}
            <ConfidenceBadge confidence={provision.confidence_score} />
            {provision.modal_verb && (
              <span className={cn(
                'text-xs px-1.5 py-0.5 rounded',
                provision.modal_verb === 'shall' || provision.modal_verb === 'must' ? 'bg-blue-100 text-blue-800' :
                provision.modal_verb === 'may' ? 'bg-gray-100 text-gray-700' :
                'bg-purple-100 text-purple-800'
              )}>{provision.modal_verb}</span>
            )}
            {provision.article_reference && (
              <span className="text-xs text-[#8a7e6d]">{provision.article_reference}</span>
            )}
          </div>
          <p className="text-sm leading-relaxed">
            {expanded
              ? highlightMatch(provision.provision_text, query)
              : highlightMatch(provision.provision_text?.slice(0, 200) + (provision.provision_text?.length > 200 ? '...' : ''), query)
            }
          </p>
          {expanded && (
            <div className="mt-2 space-y-1">
              {provision.context_before && (
                <p className="text-xs text-[#8a7e6d] italic">...{provision.context_before}</p>
              )}
              {provision.context_after && (
                <p className="text-xs text-[#8a7e6d] italic">{provision.context_after}...</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function CBASearch() {
  useEffect(() => { document.title = 'Search Contracts - The Organizer' }, [])

  const [textQuery, setTextQuery] = useState('')
  const [submittedText, setSubmittedText] = useState('')
  const [employer, setEmployer] = useState('')
  const [union, setUnion] = useState('')
  const [category, setCategory] = useState('')
  const [provisionClass, setProvisionClass] = useState('')
  const [modalVerb, setModalVerb] = useState('')
  const [minConfidence, setMinConfidence] = useState('')
  const [page, setPage] = useState(1)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [hasSearched, setHasSearched] = useState(false)

  const categoriesQuery = useCBACategories()
  const classesQuery = useCBAProvisionClasses()
  const filterOptionsQuery = useCBAFilterOptions()

  const hasAnyFilter = submittedText || employer || union || category || provisionClass || modalVerb || minConfidence

  const { data, isLoading, isError, error } = useCBAProvisionSearch({
    q: submittedText || undefined,
    category: category || undefined,
    provision_class: provisionClass || undefined,
    modal_verb: modalVerb || undefined,
    min_confidence: minConfidence ? parseFloat(minConfidence) : undefined,
    employer_name: employer || undefined,
    union_name: union || undefined,
    page,
    limit: PAGE_SIZE,
    enabled: hasSearched,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setSubmittedText(textQuery)
    setPage(1)
    setHasSearched(true)
  }

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value)
    setPage(1)
    setHasSearched(true)
  }

  const clearAll = () => {
    setTextQuery('')
    setSubmittedText('')
    setEmployer('')
    setUnion('')
    setCategory('')
    setProvisionClass('')
    setModalVerb('')
    setMinConfidence('')
    setPage(1)
    setHasSearched(false)
  }

  const activeFilterCount = [employer, union, category, provisionClass, modalVerb, minConfidence].filter(Boolean).length

  const totalPages = data?.pages || 0

  // Group results by contract
  const grouped = {}
  for (const item of (data?.results || [])) {
    const key = item.cba_id || 'unknown'
    if (!grouped[key]) {
      grouped[key] = {
        id: key,
        employer_name: item.employer_name || 'Unknown',
        union_name: item.union_name,
        provisions: [],
      }
    }
    grouped[key].provisions.push(item)
  }
  const groupedEntries = Object.values(grouped)

  const employers = filterOptionsQuery.data?.employers || []
  const unions = filterOptionsQuery.data?.unions || []
  const categories = categoriesQuery.data?.results || []
  const classes = classesQuery.data?.results || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-editorial text-3xl font-bold">Search Provisions</h1>
        {hasAnyFilter && (
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex items-center gap-1 text-sm text-[#c78c4e] hover:underline"
          >
            <X className="h-3.5 w-3.5" /> Clear all
          </button>
        )}
      </div>

      {/* Text search bar */}
      <form onSubmit={handleSubmit}>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#8a7e6d]" />
            <input
              type="text"
              value={textQuery}
              onChange={e => setTextQuery(e.target.value)}
              placeholder="Search provision text (optional -- use filters below to browse)..."
              className="w-full rounded border px-3 py-2 pl-9 text-sm bg-transparent"
            />
          </div>
          <button
            type="submit"
            className="rounded px-4 py-2 text-sm font-medium"
            style={{ backgroundColor: '#c78c4e', color: '#faf6ef' }}
          >
            Search
          </button>
        </div>
      </form>

      {/* Filter panel */}
      <div className="border rounded-lg">
        <button
          type="button"
          onClick={() => setFiltersOpen(v => !v)}
          className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-muted/20 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-[#8a7e6d]" />
            <span className="text-sm font-medium">Filters</span>
            {activeFilterCount > 0 && (
              <span className="text-xs rounded-full px-2 py-0.5 font-medium" style={{ backgroundColor: '#c78c4e', color: '#faf6ef' }}>
                {activeFilterCount}
              </span>
            )}
          </div>
          {filtersOpen ? <ChevronUp className="h-4 w-4 text-[#8a7e6d]" /> : <ChevronDown className="h-4 w-4 text-[#8a7e6d]" />}
        </button>

        {filtersOpen && (
          <div className="px-4 pb-4 pt-1 border-t">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Employer */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Employer</label>
                <select
                  value={employer}
                  onChange={handleFilterChange(setEmployer)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">All employers</option>
                  {employers.map(e => (
                    <option key={e.cba_id} value={e.name}>{e.name}</option>
                  ))}
                </select>
              </div>

              {/* Union */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Union</label>
                <select
                  value={union}
                  onChange={handleFilterChange(setUnion)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">All unions</option>
                  {unions.map(u => (
                    <option key={u.cba_id} value={u.name}>{u.name}</option>
                  ))}
                </select>
              </div>

              {/* Category */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Category</label>
                <select
                  value={category}
                  onChange={handleFilterChange(setCategory)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">All categories</option>
                  {categories.map(c => (
                    <option key={c.category_name} value={c.category_name}>
                      {c.display_name || c.category_name} ({c.provision_count || 0})
                    </option>
                  ))}
                </select>
              </div>

              {/* Provision Class */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Provision Type</label>
                <select
                  value={provisionClass}
                  onChange={handleFilterChange(setProvisionClass)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">All types</option>
                  {classes.map(c => (
                    <option key={c.provision_class} value={c.provision_class}>
                      {c.provision_class} ({c.cnt})
                    </option>
                  ))}
                </select>
              </div>

              {/* Modal Verb */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Obligation Strength</label>
                <select
                  value={modalVerb}
                  onChange={handleFilterChange(setModalVerb)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">Any</option>
                  <option value="shall">shall (binding)</option>
                  <option value="must">must (mandatory)</option>
                  <option value="will">will (commitment)</option>
                  <option value="may">may (permissive)</option>
                  <option value="should">should (advisory)</option>
                </select>
              </div>

              {/* Min Confidence */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Min. Confidence</label>
                <select
                  value={minConfidence}
                  onChange={handleFilterChange(setMinConfidence)}
                  className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                >
                  <option value="">Any</option>
                  <option value="0.9">90%+ (high)</option>
                  <option value="0.8">80%+</option>
                  <option value="0.7">70%+</option>
                  <option value="0.5">50%+</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Not yet searched */}
      {!hasSearched && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">Search contract provisions</h3>
          <p className="text-muted-foreground text-sm max-w-md">
            Enter a search term or use the filters above to browse provisions by employer, union, category, or provision type.
          </p>
        </div>
      )}

      {/* Loading */}
      {isLoading && hasSearched && (
        <div className="text-sm text-[#8a7e6d]">Searching...</div>
      )}

      {/* Error */}
      {isError && (
        <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive">
          Search failed: {error?.message || 'Unknown error'}
        </div>
      )}

      {/* Empty */}
      {hasSearched && data && (data.total || 0) === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">No provisions found</h3>
          <p className="text-muted-foreground">Try different search terms or adjust filters.</p>
        </div>
      )}

      {/* Results */}
      {hasSearched && data && (data.total || 0) > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-[#8a7e6d]">
              {(data.total || 0).toLocaleString()} provision{data.total !== 1 ? 's' : ''} found
            </p>
          </div>

          <div className="space-y-4">
            {groupedEntries.map(group => (
              <div key={group.id} className="border rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 bg-muted/30 border-b flex items-center justify-between">
                  <div>
                    <Link to={`/cbas/${group.id}`} className="font-medium text-[#c78c4e] hover:underline">
                      {group.employer_name}
                    </Link>
                    {group.union_name && (
                      <span className="text-sm text-[#8a7e6d] ml-2">-- {group.union_name}</span>
                    )}
                  </div>
                  <span className="text-xs text-[#8a7e6d]">{group.provisions.length} result{group.provisions.length !== 1 ? 's' : ''}</span>
                </div>
                <div>
                  {group.provisions.map((p, i) => (
                    <ProvisionCard key={p.provision_id || i} provision={p} query={submittedText} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#8a7e6d]">Page {page} of {totalPages}</p>
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
