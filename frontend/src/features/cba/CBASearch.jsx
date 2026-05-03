import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, SearchX, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, X, Filter, ArrowUpDown, FileText, Sparkles } from 'lucide-react'
import { useCBAProvisionSearch, useCBAArticleSearch, useCBASemanticSearch, useCBACategories, useCBACategoryGroups, useCBAProvisionClasses, useCBAFilterOptions } from '@/shared/api/cba'
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

const CATEGORY_COLORS = {
  union_security: 'bg-purple-100 text-purple-800',
  coverage: 'bg-gray-100 text-gray-800',
  wages_hours: 'bg-green-100 text-green-800',
  management_rights: 'bg-red-100 text-red-800',
  grievance: 'bg-orange-100 text-orange-800',
  arbitration: 'bg-orange-100 text-orange-800',
  job_security: 'bg-blue-100 text-blue-800',
  no_strike: 'bg-red-100 text-red-700',
  signatory: 'bg-gray-100 text-gray-700',
  benefits: 'bg-teal-100 text-teal-800',
  disability: 'bg-teal-100 text-teal-700',
  sick_leave: 'bg-teal-100 text-teal-700',
  leave: 'bg-cyan-100 text-cyan-800',
  classifications: 'bg-gray-100 text-gray-700',
  superintendents: 'bg-amber-100 text-amber-800',
  new_development: 'bg-indigo-100 text-indigo-800',
  joint_industry: 'bg-indigo-100 text-indigo-700',
  general: 'bg-gray-100 text-gray-600',
  duration: 'bg-yellow-100 text-yellow-800',
  building_acquisition: 'bg-gray-100 text-gray-700',
  safety: 'bg-red-100 text-red-700',
  technology: 'bg-violet-100 text-violet-800',
  other: 'bg-gray-100 text-gray-600',
}

function ArticleResultCard({ article, query }) {
  const [expanded, setExpanded] = useState(false)
  const colorCls = CATEGORY_COLORS[article.category] || CATEGORY_COLORS.other
  const preview = article.text?.slice(0, 500) || ''
  const hasMore = (article.text?.length || 0) > 500

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-muted/20 transition-colors"
      >
        {expanded
          ? <ChevronDown className="h-4 w-4 shrink-0 mt-0.5 text-[#8a7e6d]" />
          : <ChevronUp className="h-4 w-4 shrink-0 mt-0.5 rotate-180 text-[#8a7e6d]" />
        }
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-medium text-sm">{article.title || `Article ${article.number || '?'}`}</span>
            {article.category && (
              <span className={cn('text-xs px-2 py-0.5 rounded-full shrink-0', colorCls)}>
                {article.category.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#8a7e6d]">
            {article.employer_name && <span>{article.employer_name}</span>}
            {article.union_name && <span>-- {article.union_name}</span>}
            {article.word_count != null && <span>{article.word_count.toLocaleString()} words</span>}
            {article.page_start && (
              <span>
                p. {article.page_start}{article.page_end && article.page_end !== article.page_start ? `--${article.page_end}` : ''}
              </span>
            )}
          </div>
          {!expanded && (
            <p className="text-sm leading-relaxed mt-2 text-foreground/80">
              {highlightMatch(preview + (hasMore ? '...' : ''), query)}
            </p>
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t bg-muted/5 px-4 py-3">
          <div className="text-sm leading-relaxed whitespace-normal break-words">
            {highlightMatch(article.text, query)}
          </div>
          {article.cba_id && (
            <div className="mt-3 pt-2 border-t border-dashed">
              <Link to={`/cbas/${article.cba_id}/articles`} className="text-xs text-[#c78c4e] hover:underline">
                View full contract
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SimilarityBadge({ similarity }) {
  if (similarity == null) return null
  const pct = Math.round(similarity * 100)
  const color = pct >= 70 ? 'bg-green-100 text-green-800'
    : pct >= 50 ? 'bg-yellow-100 text-yellow-800'
    : 'bg-gray-100 text-gray-700'
  return (
    <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', color)} title={`Cosine similarity: ${similarity.toFixed(3)}`}>
      {pct}% match
    </span>
  )
}

function SemanticResultCard({ result }) {
  const [expanded, setExpanded] = useState(false)
  const isArticle = result.object_type === 'article'
  const colorCls = CATEGORY_COLORS[result.category] || CATEGORY_COLORS.other
  const preview = result.preview || ''
  const hasMore = (result.text_length || 0) > 500
  const title = result.title || (isArticle ? 'Untitled Article' : 'Provision')

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-muted/20 transition-colors"
      >
        {expanded
          ? <ChevronDown className="h-4 w-4 shrink-0 mt-0.5 text-[#8a7e6d]" />
          : <ChevronUp className="h-4 w-4 shrink-0 mt-0.5 rotate-180 text-[#8a7e6d]" />
        }
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={cn(
              'text-xs px-2 py-0.5 rounded shrink-0 font-medium',
              isArticle ? 'bg-[#c78c4e]/15 text-[#c78c4e]' : 'bg-[#2c2418]/10 text-[#2c2418]'
            )}>
              {isArticle ? 'Article' : 'Provision'}
            </span>
            <span className="font-medium text-sm">{title}</span>
            {result.category && (
              <span className={cn('text-xs px-2 py-0.5 rounded-full shrink-0', colorCls)}>
                {result.category.replace(/_/g, ' ')}
              </span>
            )}
            <SimilarityBadge similarity={result.similarity} />
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#8a7e6d]">
            {result.employer_name && <span>{result.employer_name}</span>}
            {result.union_name && <span>-- {result.union_name}</span>}
            {result.page_start && (
              <span>
                p. {result.page_start}{result.page_end && result.page_end !== result.page_start ? `--${result.page_end}` : ''}
              </span>
            )}
          </div>
          {!expanded && (
            <p className="text-sm leading-relaxed mt-2 text-foreground/80">
              {preview}{hasMore ? '...' : ''}
            </p>
          )}
        </div>
      </button>
      {expanded && (
        <div className="border-t bg-muted/5 px-4 py-3">
          <div className="text-sm leading-relaxed whitespace-normal break-words">
            {preview}
          </div>
          {result.cba_id && (
            <div className="mt-3 pt-2 border-t border-dashed flex items-center justify-between">
              <Link to={`/cbas/${result.cba_id}/articles`} className="text-xs text-[#c78c4e] hover:underline">
                View full contract
              </Link>
              {hasMore && (
                <span className="text-xs text-[#8a7e6d]">Showing first 500 chars of {result.text_length.toLocaleString()}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
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

  const [searchMode, setSearchMode] = useState('provisions')
  const [semanticTypes, setSemanticTypes] = useState('article,provision')
  const [semanticTopK, setSemanticTopK] = useState(25)
  const [textQuery, setTextQuery] = useState('')
  const [submittedText, setSubmittedText] = useState('')
  const [employer, setEmployer] = useState('')
  const [union, setUnion] = useState('')
  const [category, setCategory] = useState('')
  const [categoryGroup, setCategoryGroup] = useState('')
  const [provisionClass, setProvisionClass] = useState('')
  const [modalVerb, setModalVerb] = useState('')
  const [minConfidence, setMinConfidence] = useState('')
  const [sortBy, setSortBy] = useState('')
  const [page, setPage] = useState(1)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [hasSearched, setHasSearched] = useState(false)

  const categoriesQuery = useCBACategories()
  const categoryGroupsQuery = useCBACategoryGroups()
  const classesQuery = useCBAProvisionClasses()
  const filterOptionsQuery = useCBAFilterOptions()

  // Determine effective category filter: group takes precedence, but specific category can override
  const effectiveCategory = category || undefined
  const effectiveCategoryGroup = (!category && categoryGroup) ? categoryGroup : undefined

  const hasAnyFilter = submittedText || employer || union || category || categoryGroup || provisionClass || modalVerb || minConfidence

  // Provision search query
  const provisionQuery = useCBAProvisionSearch({
    q: submittedText || undefined,
    category: effectiveCategory,
    provision_class: provisionClass || undefined,
    modal_verb: modalVerb || undefined,
    min_confidence: minConfidence ? parseFloat(minConfidence) : undefined,
    employer_name: employer || undefined,
    union_name: union || undefined,
    page,
    limit: PAGE_SIZE,
    enabled: hasSearched && searchMode === 'provisions',
  })

  // Article search query
  const articleQuery = useCBAArticleSearch({
    q: submittedText || undefined,
    category: effectiveCategory,
    category_group: effectiveCategoryGroup,
    employer_name: employer || undefined,
    union_name: union || undefined,
    sort_by: sortBy || undefined,
    page,
    limit: PAGE_SIZE,
    enabled: hasSearched && searchMode === 'articles',
  })

  // Semantic search query (pgvector + Gemini embeddings)
  const semanticQuery = useCBASemanticSearch({
    q: submittedText || undefined,
    types: semanticTypes,
    top_k: semanticTopK,
    employer_name: employer || undefined,
    union_name: union || undefined,
    category: effectiveCategory,
    category_group: effectiveCategoryGroup,
    enabled: hasSearched && searchMode === 'semantic',
  })

  // Use the active query based on search mode
  const activeQuery = searchMode === 'provisions'
    ? provisionQuery
    : searchMode === 'articles'
      ? articleQuery
      : semanticQuery
  const { data, isLoading, isError, error } = activeQuery

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

  const handleModeSwitch = (mode) => {
    setSearchMode(mode)
    setPage(1)
    // Reset mode-specific filters
    if (mode === 'articles') {
      setProvisionClass('')
      setModalVerb('')
      setMinConfidence('')
      if (!sortBy) setSortBy(submittedText ? 'relevance' : '')
    } else if (mode === 'semantic') {
      // Semantic mode: no FTS-specific filters, no pagination
      setProvisionClass('')
      setModalVerb('')
      setMinConfidence('')
      setSortBy('')
    } else {
      setCategoryGroup('')
      setSortBy('')
    }
    if (hasSearched) setHasSearched(true)
  }

  const handleCategoryGroupChange = (e) => {
    const val = e.target.value
    setCategoryGroup(val)
    // Clear individual category when selecting a group
    if (val) setCategory('')
    setPage(1)
    setHasSearched(true)
  }

  const handleCategoryChange = (e) => {
    const val = e.target.value
    setCategory(val)
    // Clear group when selecting individual category
    if (val) setCategoryGroup('')
    setPage(1)
    setHasSearched(true)
  }

  const clearAll = () => {
    setTextQuery('')
    setSubmittedText('')
    setEmployer('')
    setUnion('')
    setCategory('')
    setCategoryGroup('')
    setProvisionClass('')
    setModalVerb('')
    setMinConfidence('')
    setSortBy('')
    setPage(1)
    setHasSearched(false)
  }

  const activeFilterCount = [employer, union, category, categoryGroup, provisionClass, modalVerb, minConfidence].filter(Boolean).length

  const totalPages = data?.pages || 0

  // Group provision results by contract
  const grouped = {}
  if (searchMode === 'provisions') {
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
  }
  const groupedEntries = Object.values(grouped)
  const articleResults = searchMode === 'articles' ? (data?.results || []) : []
  const semanticResults = searchMode === 'semantic' ? (data?.results || []) : []

  const employers = filterOptionsQuery.data?.employers || []
  const unions = filterOptionsQuery.data?.unions || []
  const categories = categoriesQuery.data?.results || []
  const classes = classesQuery.data?.results || []
  const categoryGroups = categoryGroupsQuery.data?.groups || []

  // Determine available sort options based on mode and search state
  const sortOptions = searchMode === 'provisions'
    ? [
        { value: '', label: 'Default' },
        ...(submittedText ? [{ value: 'relevance', label: 'Relevance' }] : []),
        { value: 'employer', label: 'Employer' },
        { value: 'category', label: 'Category' },
        { value: 'confidence', label: 'Confidence' },
      ]
    : [
        { value: '', label: 'Default' },
        ...(submittedText ? [{ value: 'relevance', label: 'Relevance' }] : []),
        { value: 'employer', label: 'Employer' },
        { value: 'category', label: 'Category' },
      ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-editorial text-3xl font-bold">Search Contracts</h1>
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

      {/* Search mode toggle */}
      <div className="flex items-center gap-1 p-1 rounded-lg border bg-muted/10 w-fit">
        <button
          type="button"
          onClick={() => handleModeSwitch('provisions')}
          className={cn(
            'px-4 py-1.5 rounded text-sm font-medium transition-colors',
            searchMode === 'provisions'
              ? 'bg-[#2c2418] text-[#faf6ef]'
              : 'text-[#8a7e6d] hover:text-foreground hover:bg-muted/30'
          )}
        >
          Provisions
        </button>
        <button
          type="button"
          onClick={() => handleModeSwitch('articles')}
          className={cn(
            'px-4 py-1.5 rounded text-sm font-medium transition-colors inline-flex items-center gap-1.5',
            searchMode === 'articles'
              ? 'bg-[#2c2418] text-[#faf6ef]'
              : 'text-[#8a7e6d] hover:text-foreground hover:bg-muted/30'
          )}
        >
          <FileText className="h-3.5 w-3.5" />
          Articles
        </button>
        <button
          type="button"
          onClick={() => handleModeSwitch('semantic')}
          className={cn(
            'px-4 py-1.5 rounded text-sm font-medium transition-colors inline-flex items-center gap-1.5',
            searchMode === 'semantic'
              ? 'bg-[#2c2418] text-[#faf6ef]'
              : 'text-[#8a7e6d] hover:text-foreground hover:bg-muted/30'
          )}
          title="Find clauses by meaning, not exact words"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Semantic
        </button>
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
              placeholder={searchMode === 'provisions'
                ? 'Search provision text (optional -- use filters below to browse)...'
                : searchMode === 'articles'
                  ? 'Search article text across all contracts...'
                  : 'Describe what you want to find in plain English, e.g. "clauses requiring advance notice of layoffs"...'
              }
              className="w-full rounded border px-3 py-2 pl-9 text-sm bg-transparent"
            />
          </div>
          <button
            type="submit"
            className="rounded px-4 py-2 text-sm font-medium bg-[#c78c4e] text-[#faf6ef]"
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
              <span className="text-xs rounded-full px-2 py-0.5 font-medium bg-[#c78c4e] text-[#faf6ef]">
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

              {/* Category Group (available for both modes) */}
              {categoryGroups.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Category Group</label>
                  <select
                    value={categoryGroup}
                    onChange={handleCategoryGroupChange}
                    className="w-full rounded border px-3 py-1.5 text-sm bg-transparent"
                  >
                    <option value="">All groups</option>
                    {categoryGroups.map(g => (
                      <option key={g.group_name} value={g.group_name}>
                        {g.display_name || g.group_name} ({g.category_count || 0})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Category (individual) */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Category</label>
                <select
                  value={category}
                  onChange={handleCategoryChange}
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

              {/* Provision Class (provisions mode only) */}
              {searchMode === 'provisions' && (
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
              )}

              {/* Modal Verb (provisions mode only) */}
              {searchMode === 'provisions' && (
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
              )}

              {/* Min Confidence (provisions mode only) */}
              {searchMode === 'provisions' && (
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
              )}

              {/* Sort dropdown */}
              <div>
                <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Sort by</label>
                <div className="relative">
                  <ArrowUpDown className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#8a7e6d]" />
                  <select
                    value={sortBy}
                    onChange={handleFilterChange(setSortBy)}
                    className="w-full rounded border px-3 py-1.5 pl-8 text-sm bg-transparent"
                  >
                    {sortOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Not yet searched */}
      {!hasSearched && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          {searchMode === 'semantic'
            ? <Sparkles className="h-12 w-12 text-[#c78c4e] mb-4" />
            : <Search className="h-12 w-12 text-muted-foreground mb-4" />
          }
          <h3 className="font-editorial text-lg font-semibold mb-1">
            {searchMode === 'semantic' ? 'Semantic search' : `Search contract ${searchMode === 'provisions' ? 'provisions' : 'articles'}`}
          </h3>
          <p className="text-muted-foreground text-sm max-w-md">
            {searchMode === 'provisions'
              ? 'Enter a search term or use the filters above to browse provisions by employer, union, category, or provision type.'
              : searchMode === 'articles'
                ? 'Search full article text across all contracts. Use category groups or individual categories to narrow results.'
                : 'Find articles and provisions by meaning, not exact words. Ask natural-language questions like "pension vesting rules" or "protection against outsourcing" -- results are ranked by how closely they match the idea, not the keywords.'
            }
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
      {hasSearched && data
        && ((searchMode === 'semantic' ? (data.result_count || 0) : (data.total || 0)) === 0)
        && !isLoading && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="font-editorial text-lg font-semibold mb-1">
            No {searchMode === 'provisions' ? 'provisions' : searchMode === 'articles' ? 'articles' : 'matches'} found
          </h3>
          <p className="text-muted-foreground">Try different search terms or adjust filters.</p>
        </div>
      )}

      {/* Provision results */}
      {hasSearched && searchMode === 'provisions' && data && (data.total || 0) > 0 && (
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
        </>
      )}

      {/* Article results */}
      {hasSearched && searchMode === 'articles' && data && (data.total || 0) > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-[#8a7e6d]">
              {(data.total || 0).toLocaleString()} article{data.total !== 1 ? 's' : ''} found
            </p>
          </div>

          <div className="space-y-2">
            {articleResults.map((article, i) => (
              <ArticleResultCard
                key={article.section_id || article.article_id || i}
                article={article}
                query={submittedText}
              />
            ))}
          </div>
        </>
      )}

      {/* Semantic results */}
      {hasSearched && searchMode === 'semantic' && data && (data.result_count || 0) > 0 && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm text-[#8a7e6d]">
              Top {data.result_count} match{data.result_count !== 1 ? 'es' : ''} for <span className="font-medium text-foreground">&ldquo;{data.query}&rdquo;</span>
              {data.search_time_ms != null && (
                <span className="ml-2 text-xs">(embed {data.embedding_time_ms}ms + search {data.search_time_ms}ms)</span>
              )}
            </p>
            <div className="flex items-center gap-2">
              <label className="text-xs text-[#8a7e6d]">Include:</label>
              <select
                value={semanticTypes}
                onChange={e => { setSemanticTypes(e.target.value); setHasSearched(true) }}
                className="rounded border px-2 py-1 text-xs bg-transparent"
              >
                <option value="article,provision">Both</option>
                <option value="article">Articles only</option>
                <option value="provision">Provisions only</option>
              </select>
              <label className="text-xs text-[#8a7e6d] ml-2">Top K:</label>
              <select
                value={semanticTopK}
                onChange={e => { setSemanticTopK(parseInt(e.target.value, 10)); setHasSearched(true) }}
                className="rounded border px-2 py-1 text-xs bg-transparent"
              >
                <option value="10">10</option>
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            {semanticResults.map((result, i) => (
              <SemanticResultCard
                key={`${result.object_type}-${result.object_id || i}`}
                result={result}
              />
            ))}
          </div>
        </>
      )}

      {/* Pagination (provisions/articles only — semantic uses top_k) */}
      {hasSearched && searchMode !== 'semantic' && data && totalPages > 1 && (
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
    </div>
  )
}
