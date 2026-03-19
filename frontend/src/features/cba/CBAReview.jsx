import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
  Check, X, Edit3, Filter, BarChart3, FileText, AlertTriangle,
} from 'lucide-react'
import {
  useCBAReviewQueue, useCBAReviewStats, useCBARules, useCBACategories,
  useSubmitCBAReview, useCBAProvisionClasses,
} from '@/shared/api/cba'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 15

function ConfidenceBadge({ confidence }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const color = pct >= 80 ? 'bg-green-100 text-green-800'
    : pct >= 60 ? 'bg-yellow-100 text-yellow-800'
    : 'bg-red-100 text-red-800'
  return <span className={cn('text-xs px-1.5 py-0.5 rounded font-mono', color)}>{pct}%</span>
}

function ReviewActionBadge({ action }) {
  if (!action) return null
  const map = {
    approve: { label: 'Approved', cls: 'bg-green-100 text-green-800' },
    reject: { label: 'Rejected', cls: 'bg-red-100 text-red-800' },
    correct: { label: 'Corrected', cls: 'bg-blue-100 text-blue-800' },
    recategorize: { label: 'Recategorized', cls: 'bg-blue-100 text-blue-800' },
  }
  const m = map[action] || { label: action, cls: 'bg-gray-100 text-gray-700' }
  return <span className={cn('text-xs px-1.5 py-0.5 rounded', m.cls)}>{m.label}</span>
}

function StatsBar({ stats }) {
  if (!stats) return null
  const { total_provisions, verified, unreviewed } = stats
  const pct = total_provisions > 0 ? Math.round((verified / total_provisions) * 100) : 0

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-medium flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-[#8a7e6d]" /> Review Progress
        </h2>
        <span className="text-sm text-[#8a7e6d]">{verified} / {total_provisions} reviewed ({pct}%)</span>
      </div>
      <div className="w-full bg-muted rounded-full h-2">
        <div className="bg-[#c78c4e] h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center text-sm">
        <div className="border rounded p-2">
          <div className="text-lg font-bold">{total_provisions}</div>
          <div className="text-xs text-[#8a7e6d]">Total</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-amber-600">{unreviewed}</div>
          <div className="text-xs text-[#8a7e6d]">Unreviewed</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-green-600">{stats.action_counts?.approve || 0}</div>
          <div className="text-xs text-[#8a7e6d]">Approved</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-red-600">{stats.action_counts?.reject || 0}</div>
          <div className="text-xs text-[#8a7e6d]">Rejected</div>
        </div>
      </div>
    </div>
  )
}

function RuleSidebar({ rules, ruleStats, selectedRule, onSelectRule, selectedCategory, onSelectCategory }) {
  const categories = [...new Set((rules || []).map(r => r.category))].sort()

  const filteredRules = selectedCategory
    ? (rules || []).filter(r => r.category === selectedCategory)
    : (rules || [])

  // Build flat list of rules with stats
  const ruleList = []
  for (const rule of filteredRules) {
    for (const tp of (rule.text_patterns || [])) {
      const stat = ruleStats?.[tp.name]
      ruleList.push({
        name: tp.name,
        category: rule.category,
        provision_class: tp.provision_class,
        confidence: tp.confidence,
        summary: tp.summary,
        match_count: stat?.match_count || 0,
        verified_count: stat?.verified_count || 0,
      })
    }
  }
  ruleList.sort((a, b) => b.match_count - a.match_count)

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-muted/30 border-b">
        <h3 className="text-sm font-medium">Rules by Category</h3>
      </div>
      <div className="px-2 py-2 border-b">
        <select
          value={selectedCategory}
          onChange={e => { onSelectCategory(e.target.value); onSelectRule('') }}
          className="w-full rounded border px-2 py-1 text-sm bg-transparent"
        >
          <option value="">All categories</option>
          {categories.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <div className="max-h-[500px] overflow-y-auto divide-y">
        <button
          type="button"
          onClick={() => onSelectRule('')}
          className={cn(
            'w-full text-left px-3 py-2 text-sm hover:bg-muted/20 transition-colors',
            !selectedRule && 'bg-[#c78c4e]/10 font-medium'
          )}
        >
          All rules
        </button>
        {ruleList.map(r => (
          <button
            key={r.name}
            type="button"
            onClick={() => onSelectRule(r.name)}
            className={cn(
              'w-full text-left px-3 py-2 hover:bg-muted/20 transition-colors',
              selectedRule === r.name && 'bg-[#c78c4e]/10'
            )}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-sm truncate">{r.name}</span>
              <span className="text-xs text-[#8a7e6d] shrink-0">{r.match_count}</span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-xs text-[#8a7e6d]">{r.category}</span>
              {r.verified_count > 0 && (
                <span className="text-xs text-green-600">{r.verified_count} reviewed</span>
              )}
            </div>
          </button>
        ))}
        {ruleList.length === 0 && (
          <div className="px-3 py-4 text-sm text-[#8a7e6d] text-center">No rules found</div>
        )}
      </div>
    </div>
  )
}

function ReviewCard({ provision, onReview, categories, provisionClasses }) {
  const [expanded, setExpanded] = useState(false)
  const [showCorrect, setShowCorrect] = useState(false)
  const [correctedCategory, setCorrectedCategory] = useState(provision.category || '')
  const [correctedClass, setCorrectedClass] = useState(provision.provision_class || '')
  const [notes, setNotes] = useState('')

  const submitReview = useSubmitCBAReview()

  const handleAction = (action) => {
    const payload = {
      provisionId: provision.provision_id,
      review_action: action,
      notes: notes || undefined,
    }
    if (action === 'correct') {
      payload.corrected_category = correctedCategory
      payload.corrected_class = correctedClass
    }
    submitReview.mutate(payload)
    if (onReview) onReview(provision.provision_id, action)
    setShowCorrect(false)
    setNotes('')
  }

  const isReviewed = !!provision.review_action

  return (
    <div className={cn(
      'border rounded-lg overflow-hidden transition-colors',
      isReviewed && 'opacity-60',
    )}>
      {/* Header */}
      <div className="px-4 py-2.5 bg-muted/20 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <button type="button" onClick={() => setExpanded(v => !v)} className="shrink-0 text-[#8a7e6d] hover:text-foreground">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <span className="text-xs rounded-full border px-2 py-0.5 font-medium">{provision.category}</span>
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
          {provision.review_action && <ReviewActionBadge action={provision.review_action} />}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-xs text-[#8a7e6d] hidden sm:inline">
            {provision.employer_name_raw} -- {provision.rule_name}
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">
          {provision.provision_text}
        </p>

        {expanded && (
          <div className="mt-2 space-y-1">
            {provision.context_before && (
              <p className="text-xs text-[#8a7e6d] italic border-l-2 border-[#8a7e6d]/30 pl-2">...{provision.context_before?.slice(-300)}</p>
            )}
            {provision.context_after && (
              <p className="text-xs text-[#8a7e6d] italic border-l-2 border-[#8a7e6d]/30 pl-2">{provision.context_after?.slice(0, 300)}...</p>
            )}
            <div className="flex gap-3 text-xs text-[#8a7e6d] mt-2">
              <span>Rule: <span className="font-mono">{provision.rule_name}</span></span>
              <span>Page: {provision.page_start}{provision.page_end && provision.page_end !== provision.page_start ? `-${provision.page_end}` : ''}</span>
              {provision.article_reference && <span>Ref: {provision.article_reference}</span>}
              <Link to={`/cbas/${provision.cba_id}`} className="text-[#c78c4e] hover:underline">View contract</Link>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-4 py-2 border-t bg-muted/10 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => handleAction('approve')}
          disabled={submitReview.isPending}
          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100 border border-green-200 transition-colors disabled:opacity-50"
        >
          <Check className="h-3 w-3" /> Approve
        </button>
        <button
          type="button"
          onClick={() => handleAction('reject')}
          disabled={submitReview.isPending}
          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition-colors disabled:opacity-50"
        >
          <X className="h-3 w-3" /> Reject
        </button>
        <button
          type="button"
          onClick={() => setShowCorrect(v => !v)}
          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 transition-colors"
        >
          <Edit3 className="h-3 w-3" /> Correct
        </button>
        <div className="flex-1" />
        <input
          type="text"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Notes (optional)..."
          className="rounded border px-2 py-1 text-xs bg-transparent w-48"
        />
        {provision.review_notes && (
          <span className="text-xs text-[#8a7e6d] italic">Previous: {provision.review_notes}</span>
        )}
      </div>

      {/* Correction panel */}
      {showCorrect && (
        <div className="px-4 py-3 border-t bg-blue-50/30 space-y-2">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Correct Category</label>
              <select
                value={correctedCategory}
                onChange={e => { setCorrectedCategory(e.target.value); if (e.target.value === 'other') setCorrectedClass('other') }}
                className="w-full rounded border px-2 py-1 text-sm bg-transparent"
              >
                {(categories || []).map(c => (
                  <option key={c.category_name} value={c.category_name}>{c.display_name || c.category_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[#8a7e6d] mb-1">Correct Provision Class</label>
              <select
                value={correctedClass}
                onChange={e => setCorrectedClass(e.target.value)}
                className="w-full rounded border px-2 py-1 text-sm bg-transparent"
              >
                <option value="">-- select --</option>
                <option value="other">other</option>
                {(provisionClasses || []).filter(c => c.provision_class !== 'other').map(c => (
                  <option key={c.provision_class} value={c.provision_class}>{c.provision_class}</option>
                ))}
              </select>
            </div>
          </div>
          {correctedCategory === 'other' && (
            <div>
              <label className="block text-xs font-medium text-amber-700 mb-1">
                Describe what this provision is about (required for "other")
              </label>
              <input
                type="text"
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="e.g. safety committee, travel reimbursement, tool allowance..."
                className="w-full rounded border border-amber-300 px-2 py-1.5 text-sm bg-amber-50/50"
              />
            </div>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => handleAction('correct')}
              disabled={submitReview.isPending || (correctedCategory === 'other' && !notes.trim())}
              className="rounded px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: '#c78c4e' }}
            >
              Save Correction
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function CBAReview() {
  useEffect(() => { document.title = 'Rule Review - The Organizer' }, [])

  const [category, setCategory] = useState('')
  const [ruleName, setRuleName] = useState('')
  const [reviewStatus, setReviewStatus] = useState('unreviewed')
  const [confidenceBand, setConfidenceBand] = useState('')
  const [page, setPage] = useState(1)
  const [view, setView] = useState('queue') // 'queue' | 'stats'

  // Parse confidence band
  let minConf, maxConf
  if (confidenceBand === 'low') { minConf = 0; maxConf = 0.7 }
  else if (confidenceBand === 'mid') { minConf = 0.7; maxConf = 0.85 }
  else if (confidenceBand === 'high') { minConf = 0.85; maxConf = 1 }

  const statsQuery = useCBAReviewStats()
  const rulesQuery = useCBARules()
  const categoriesQuery = useCBACategories()
  const classesQuery = useCBAProvisionClasses()
  const queueQuery = useCBAReviewQueue({
    category: category || undefined,
    rule_name: ruleName || undefined,
    review_status: reviewStatus,
    min_confidence: minConf,
    max_confidence: maxConf,
    page,
    limit: PAGE_SIZE,
    sort: 'confidence_score',
    order: 'asc',
  })

  const stats = statsQuery.data
  const rules = rulesQuery.data?.rules || []
  const ruleStats = rulesQuery.data?.rule_stats || {}
  const categories = categoriesQuery.data?.results || []
  const provisionClasses = classesQuery.data?.results || []
  const queue = queueQuery.data
  const totalPages = queue?.pages || 0

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-editorial text-3xl font-bold">Rule Review</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setView('queue')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium border transition-colors',
              view === 'queue' ? 'bg-[#c78c4e] text-[#faf6ef] border-[#c78c4e]' : 'hover:bg-muted/30'
            )}
          >
            <FileText className="h-4 w-4" /> Review Queue
          </button>
          <button
            type="button"
            onClick={() => setView('stats')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium border transition-colors',
              view === 'stats' ? 'bg-[#c78c4e] text-[#faf6ef] border-[#c78c4e]' : 'hover:bg-muted/30'
            )}
          >
            <BarChart3 className="h-4 w-4" /> Rule Stats
          </button>
        </div>
      </div>

      <StatsBar stats={stats} />

      {view === 'stats' && (
        <div className="space-y-4">
          {/* Per-rule stats table */}
          <div className="border rounded-lg overflow-hidden">
            <div className="px-4 py-2.5 bg-muted/30 border-b">
              <h3 className="font-medium">Rule Performance</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/10">
                    <th className="text-left px-3 py-2 font-medium">Rule</th>
                    <th className="text-left px-3 py-2 font-medium">Category</th>
                    <th className="text-right px-3 py-2 font-medium">Matches</th>
                    <th className="text-right px-3 py-2 font-medium">Avg Conf</th>
                    <th className="text-right px-3 py-2 font-medium text-green-700">Approved</th>
                    <th className="text-right px-3 py-2 font-medium text-red-700">Rejected</th>
                    <th className="text-right px-3 py-2 font-medium text-blue-700">Corrected</th>
                    <th className="text-right px-3 py-2 font-medium">Reviewed</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(stats?.by_rule || []).map(r => {
                    const reviewedPct = r.total > 0 ? Math.round((r.reviewed / r.total) * 100) : 0
                    return (
                      <tr key={r.rule_name} className="hover:bg-muted/10">
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => { setRuleName(r.rule_name); setView('queue'); setPage(1) }}
                            className="text-[#c78c4e] hover:underline font-mono text-xs"
                          >
                            {r.rule_name}
                          </button>
                        </td>
                        <td className="px-3 py-2 text-xs">{r.category}</td>
                        <td className="px-3 py-2 text-right">{r.total}</td>
                        <td className="px-3 py-2 text-right">
                          <ConfidenceBadge confidence={r.avg_confidence} />
                        </td>
                        <td className="px-3 py-2 text-right text-green-700">{r.accepted || 0}</td>
                        <td className="px-3 py-2 text-right text-red-700">{r.rejected || 0}</td>
                        <td className="px-3 py-2 text-right text-blue-700">{r.corrected || 0}</td>
                        <td className="px-3 py-2 text-right">
                          <span className="text-xs">{reviewedPct}%</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {view === 'queue' && (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          {/* Sidebar */}
          <div className="space-y-3">
            <RuleSidebar
              rules={rules}
              ruleStats={ruleStats}
              selectedRule={ruleName}
              onSelectRule={r => { setRuleName(r); setPage(1) }}
              selectedCategory={category}
              onSelectCategory={c => { setCategory(c); setPage(1) }}
            />

            {/* Filters */}
            <div className="border rounded-lg p-3 space-y-2">
              <h3 className="text-sm font-medium flex items-center gap-1.5">
                <Filter className="h-3.5 w-3.5 text-[#8a7e6d]" /> Filters
              </h3>
              <div>
                <label className="block text-xs text-[#8a7e6d] mb-0.5">Review Status</label>
                <select
                  value={reviewStatus}
                  onChange={e => { setReviewStatus(e.target.value); setPage(1) }}
                  className="w-full rounded border px-2 py-1 text-sm bg-transparent"
                >
                  <option value="unreviewed">Unreviewed</option>
                  <option value="reviewed">Reviewed</option>
                  <option value="all">All</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-[#8a7e6d] mb-0.5">Confidence Band</label>
                <select
                  value={confidenceBand}
                  onChange={e => { setConfidenceBand(e.target.value); setPage(1) }}
                  className="w-full rounded border px-2 py-1 text-sm bg-transparent"
                >
                  <option value="">All</option>
                  <option value="low">Low (0-70%)</option>
                  <option value="mid">Medium (70-85%)</option>
                  <option value="high">High (85-100%)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Main review area */}
          <div className="space-y-3">
            {/* Queue header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <p className="text-sm text-[#8a7e6d]">
                  {queue?.total || 0} provision{queue?.total !== 1 ? 's' : ''}
                  {ruleName && <> for <span className="font-mono">{ruleName}</span></>}
                </p>
                {ruleName && (
                  <button
                    type="button"
                    onClick={() => setRuleName('')}
                    className="text-xs text-[#c78c4e] hover:underline"
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="text-xs text-[#8a7e6d]">
                Sorted by confidence (lowest first)
              </div>
            </div>

            {/* Loading */}
            {queueQuery.isLoading && (
              <div className="text-sm text-[#8a7e6d] py-8 text-center">Loading...</div>
            )}

            {/* Error */}
            {queueQuery.isError && (
              <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Failed to load: {queueQuery.error?.message || 'Unknown error'}
              </div>
            )}

            {/* Empty */}
            {queue && queue.total === 0 && !queueQuery.isLoading && (
              <div className="py-12 text-center">
                <Check className="h-12 w-12 text-green-500 mx-auto mb-3" />
                <h3 className="font-editorial text-lg font-semibold mb-1">
                  {reviewStatus === 'unreviewed' ? 'All caught up!' : 'No provisions found'}
                </h3>
                <p className="text-sm text-[#8a7e6d]">
                  {reviewStatus === 'unreviewed'
                    ? 'Every provision matching your filters has been reviewed.'
                    : 'Try adjusting your filters.'}
                </p>
              </div>
            )}

            {/* Cards */}
            {(queue?.results || []).map(p => (
              <ReviewCard
                key={p.provision_id}
                provision={p}
                categories={categories}
                provisionClasses={provisionClasses}
              />
            ))}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2">
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
        </div>
      )}
    </div>
  )
}
