import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
  Check, X, Edit3, Filter, BarChart3, FileText, AlertTriangle, Award,
  Building2, Users, HardHat, DollarSign, Briefcase, ClipboardCheck, Database,
  MapPin, Crown, Network, Star, Search,
} from 'lucide-react'
import {
  useGoldReviewQueue, useGoldReviewStats, useSectionReviews,
  useSubmitSectionReview, useMarkGoldStandard, useUnmarkGoldStandard,
  useResearchResult,
} from '@/shared/api/research'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 15

const SECTION_ORDER = [
  'identity', 'corporate_structure', 'locations', 'leadership',
  'labor', 'assessment', 'workforce', 'workplace', 'financial', 'sources',
]

const SECTION_META = {
  identity:            { icon: Building2,      label: 'Company Identity' },
  corporate_structure: { icon: Network,        label: 'Corporate Structure' },
  locations:           { icon: MapPin,         label: 'Locations' },
  leadership:          { icon: Crown,          label: 'Leadership' },
  labor:               { icon: Users,          label: 'Labor Relations' },
  workforce:           { icon: Briefcase,      label: 'Workforce' },
  workplace:           { icon: HardHat,        label: 'Workplace Safety' },
  financial:           { icon: DollarSign,     label: 'Financial' },
  assessment:          { icon: ClipboardCheck, label: 'Overall Assessment' },
  sources:             { icon: Database,       label: 'Data Sources' },
}

const KEY_LABELS = {
  legal_name: 'Legal Name', dba_names: 'DBA Names', naics_code: 'NAICS', naics_description: 'Industry',
  company_type: 'Type', union_names: 'Unions Present', nlrb_election_count: 'NLRB Elections',
  nlrb_ulp_count: 'ULP Charges', existing_contracts: 'Union Contracts',
  nlrb_election_details: 'Election Details', voluntary_recognition: 'Voluntary Recognitions',
  osha_violation_count: 'OSHA Violations', osha_serious_count: 'Serious Violations',
  osha_penalty_total: 'Total Penalties', osha_violation_details: 'Violation Details',
  whd_case_count: 'WHD Cases', workforce_composition: 'Workforce Composition',
  demographic_profile: 'Demographics', federal_contract_count: 'Federal Contracts',
  federal_obligations: 'Federal Obligations', organizing_summary: 'Summary',
  campaign_strengths: 'Strengths', campaign_challenges: 'Challenges',
  recommended_approach: 'Recommended Approach', similar_organized: 'Similar Organized Employers',
  source_list: 'Sources Used', data_gaps: 'Data Gaps', section_confidence: 'Confidence by Section',
  employee_count: 'Employees', revenue: 'Revenue', parent_company: 'Parent Company',
  hq_address: 'HQ Address', website_url: 'Website', year_founded: 'Founded',
  major_locations: 'Major Locations', parent_type: 'Parent Type',
  subsidiaries: 'Subsidiaries', corporate_family: 'Corporate Family',
  ceo: 'CEO/President', executives: 'Executive Team',
  registered_agent: 'Registered Agent', company_officers: 'Officers',
  political_donations: 'Political Donations', warn_notices: 'WARN Notices',
  local_subsidies: 'Taxpayer Subsidies', solidarity_network: 'Solidarity Network',
}

function labelFor(key) {
  return KEY_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function qualityColor(score) {
  if (score == null) return ''
  if (score >= 7) return 'text-[#3a7d44]'
  if (score >= 5) return 'text-[#c78c4e]'
  return 'text-[#c23a22]'
}

// ── Progress bar ──────────────────────────────────────────────────────────
function StatsBar({ stats }) {
  if (!stats) return null
  const { gold_standard_count, goal, total_completed, in_progress_count, unreviewed_count } = stats
  const pct = goal > 0 ? Math.round((gold_standard_count / goal) * 100) : 0

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-medium flex items-center gap-2">
          <Award className="h-4 w-4 text-[#c78c4e]" /> Gold Standard Progress
        </h2>
        <span className="text-sm text-[#8a7e6d]">{gold_standard_count} / {goal} gold standard ({pct}%)</span>
      </div>
      <div className="w-full bg-muted rounded-full h-2">
        <div className="bg-[#c78c4e] h-2 rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center text-sm">
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-[#c78c4e]">{gold_standard_count}</div>
          <div className="text-xs text-[#8a7e6d]">Gold Standard</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-blue-600">{in_progress_count}</div>
          <div className="text-xs text-[#8a7e6d]">In Progress</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold text-amber-600">{unreviewed_count}</div>
          <div className="text-xs text-[#8a7e6d]">Unreviewed</div>
        </div>
        <div className="border rounded p-2">
          <div className="text-lg font-bold">{total_completed}</div>
          <div className="text-xs text-[#8a7e6d]">Total Completed</div>
        </div>
      </div>
    </div>
  )
}

// ── Run sidebar ───────────────────────────────────────────────────────────
function RunSidebar({ runs, selectedRunId, onSelectRun }) {
  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-muted/30 border-b">
        <h3 className="text-sm font-medium">Research Runs</h3>
      </div>
      <div className="max-h-[600px] overflow-y-auto divide-y">
        {(runs || []).map(r => {
          const reviewed = r.sections_reviewed || 0
          const isGold = r.is_gold_standard
          return (
            <button
              key={r.id}
              type="button"
              onClick={() => onSelectRun(r.id)}
              className={cn(
                'w-full text-left px-3 py-2.5 hover:bg-muted/20 transition-colors',
                selectedRunId === r.id && 'bg-[#c78c4e]/10',
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-sm font-medium truncate flex items-center gap-1.5">
                  {isGold && <Star className="h-3 w-3 text-[#c78c4e] fill-[#c78c4e] shrink-0" />}
                  {r.company_name}
                </span>
                <span className={cn(
                  'text-xs shrink-0 font-mono',
                  qualityColor(r.overall_quality_score),
                )}>
                  {r.overall_quality_score != null ? Number(r.overall_quality_score).toFixed(1) : '-'}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-[#8a7e6d]">{reviewed}/10 sections</span>
                {reviewed >= 10 && !isGold && (
                  <span className="text-[10px] px-1 py-0.5 bg-green-100 text-green-700 rounded">ready</span>
                )}
                {isGold && (
                  <span className="text-[10px] px-1 py-0.5 bg-[#c78c4e]/15 text-[#c78c4e] rounded">gold</span>
                )}
                {reviewed > 0 && reviewed < 10 && (
                  <span className="text-[10px] px-1 py-0.5 bg-blue-100 text-blue-700 rounded">{reviewed} done</span>
                )}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-[#8a7e6d]">
                {r.sections_approved > 0 && <span className="text-green-600">{r.sections_approved} ok</span>}
                {r.sections_rejected > 0 && <span className="text-red-600">{r.sections_rejected} rej</span>}
                {r.sections_corrected > 0 && <span className="text-blue-600">{r.sections_corrected} fix</span>}
              </div>
            </button>
          )
        })}
        {(!runs || runs.length === 0) && (
          <div className="px-3 py-4 text-sm text-[#8a7e6d] text-center">No runs found</div>
        )}
      </div>
    </div>
  )
}

// ── Render values (from DossierSection pattern) ───────────────────────────
function RenderValue({ value }) {
  if (value == null) return <span className="text-muted-foreground">-</span>
  if (typeof value === 'string') {
    if (value.length > 200) return <p className="text-sm whitespace-pre-wrap">{value}</p>
    return <span>{value}</span>
  }
  if (typeof value === 'number') return <span>{value.toLocaleString()}</span>
  if (typeof value === 'boolean') return <span>{value ? 'Yes' : 'No'}</span>
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
    return (
      <ul className="list-disc list-inside space-y-0.5">
        {value.map((item, i) => <li key={i} className="text-sm">{item}</li>)}
      </ul>
    )
  }
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
    const cols = [...new Set(value.flatMap(obj => Object.keys(obj)))].slice(0, 6)
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs border">
          <thead>
            <tr className="bg-muted/50">
              {cols.map(col => (
                <th key={col} className="px-2 py-1 text-left font-medium text-muted-foreground whitespace-nowrap">
                  {labelFor(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {value.slice(0, 10).map((row, i) => (
              <tr key={i} className="border-t">
                {cols.map(col => (
                  <td key={col} className="px-2 py-1 whitespace-nowrap max-w-[200px] truncate">
                    {row[col] == null ? '-' : typeof row[col] === 'object' ? JSON.stringify(row[col]) : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {value.length > 10 && <p className="text-xs text-muted-foreground mt-1">Showing 10 of {value.length}</p>}
      </div>
    )
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    return (
      <dl className="space-y-0.5">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex gap-2 text-sm">
            <dt className="font-medium text-muted-foreground whitespace-nowrap">{labelFor(k)}:</dt>
            <dd><RenderValue value={v} /></dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span>{String(value)}</span>
}

// ── Section review card ───────────────────────────────────────────────────
function SectionReviewCard({ sectionKey, narrative, facts, existingReview, onSubmitReview, isPending }) {
  const meta = SECTION_META[sectionKey] || { icon: Database, label: labelFor(sectionKey) }
  const Icon = meta.icon
  const [expanded, setExpanded] = useState(true)
  const [showCorrect, setShowCorrect] = useState(false)
  const [notes, setNotes] = useState(existingReview?.reviewer_notes || '')

  // Count items
  const factCount = facts?.length || 0
  const narrativeKeys = narrative && typeof narrative === 'object' && !Array.isArray(narrative)
    ? Object.keys(narrative).length : 0
  const itemCount = factCount + narrativeKeys

  // Skip empty sections
  if (!narrative && factCount === 0) return null

  const reviewBadge = existingReview?.review_action
  const badgeMap = {
    approve: { label: 'Approved', cls: 'bg-green-100 text-green-800 border-green-200' },
    reject: { label: 'Rejected', cls: 'bg-red-100 text-red-800 border-red-200' },
    correct: { label: 'Needs Correction', cls: 'bg-blue-100 text-blue-800 border-blue-200' },
  }

  function handleAction(action) {
    onSubmitReview({
      section: sectionKey,
      review_action: action,
      reviewer_notes: notes || undefined,
    })
    setShowCorrect(false)
  }

  return (
    <div className={cn(
      'border rounded-lg overflow-hidden transition-colors',
      reviewBadge && 'opacity-75',
    )}>
      {/* Header */}
      <div className="px-4 py-2.5 bg-muted/20 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <button type="button" onClick={() => setExpanded(v => !v)} className="shrink-0 text-[#8a7e6d] hover:text-foreground">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          <Icon className="h-4 w-4 text-[#8a7e6d] shrink-0" />
          <span className="text-sm font-medium">{meta.label}</span>
          <span className="text-xs text-[#8a7e6d]">({itemCount} item{itemCount !== 1 ? 's' : ''})</span>
          {reviewBadge && (
            <span className={cn('text-xs px-1.5 py-0.5 rounded border', badgeMap[reviewBadge]?.cls)}>
              {badgeMap[reviewBadge]?.label}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="px-4 py-3">
          {/* Narrative content */}
          {narrative && typeof narrative === 'string' && (
            <p className="text-sm whitespace-pre-wrap mb-3">{narrative}</p>
          )}
          {narrative && typeof narrative === 'object' && !Array.isArray(narrative) && (
            <div className="space-y-3 mb-3">
              {Object.entries(narrative).map(([key, val]) => (
                <div key={key}>
                  <h4 className="text-sm font-semibold mb-0.5">{labelFor(key)}</h4>
                  <div className="pl-1">
                    <RenderValue value={val} />
                  </div>
                </div>
              ))}
            </div>
          )}
          {narrative && Array.isArray(narrative) && (
            <div className="mb-3"><RenderValue value={narrative} /></div>
          )}

          {/* Facts */}
          {facts && facts.length > 0 && (
            <div className="mt-2">
              <h4 className="text-xs font-semibold text-muted-foreground mb-1 uppercase tracking-wide">Extracted Facts</h4>
              <div className="space-y-1">
                {facts.map((fact, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm py-1 border-b last:border-0">
                    <span className="font-medium text-[#8a7e6d] whitespace-nowrap min-w-[140px]">
                      {fact.display_name || fact.attribute_name}
                    </span>
                    <span className="flex-1">{fact.attribute_value || '-'}</span>
                    <span className="text-[10px] text-[#8a7e6d] whitespace-nowrap">{fact.source_name || ''}</span>
                    {fact.confidence != null && (
                      <span className={cn(
                        'text-[10px] px-1 py-0.5 rounded font-mono',
                        fact.confidence >= 0.7 ? 'bg-green-100 text-green-700'
                          : fact.confidence >= 0.4 ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-red-100 text-red-700'
                      )}>
                        {Math.round(fact.confidence * 100)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Previous correction notes */}
          {existingReview?.reviewer_notes && (
            <div className="mt-3 p-2 bg-blue-50/50 rounded border border-blue-100 text-sm">
              <span className="text-xs font-medium text-blue-700">Previous notes: </span>
              <span className="text-blue-900">{existingReview.reviewer_notes}</span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="px-4 py-2 border-t bg-muted/10 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => handleAction('approve')}
          disabled={isPending}
          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100 border border-green-200 transition-colors disabled:opacity-50"
        >
          <Check className="h-3 w-3" /> Approve
        </button>
        <button
          type="button"
          onClick={() => handleAction('reject')}
          disabled={isPending}
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
      </div>

      {/* Correction panel */}
      {showCorrect && (
        <div className="px-4 py-3 border-t bg-blue-50/30 space-y-2">
          <label className="block text-xs font-medium text-[#8a7e6d] mb-1">
            What needs to change in this section?
          </label>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Describe what's wrong and how it should be corrected..."
            rows={3}
            className="w-full rounded border px-2 py-1.5 text-sm bg-transparent resize-y"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => handleAction('correct')}
              disabled={isPending || !notes.trim()}
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

// ── Action log (compact) ──────────────────────────────────────────────────
function CompactActionLog({ actions }) {
  const [expanded, setExpanded] = useState(false)
  if (!actions || actions.length === 0) return null

  const foundCount = actions.filter(a => a.data_found).length

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full px-4 py-2.5 bg-muted/20 flex items-center justify-between gap-2 hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-[#8a7e6d]" />
          <span className="text-sm font-medium">Tool Calls</span>
          <span className="text-xs text-[#8a7e6d]">({foundCount}/{actions.length} found data)</span>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-[#8a7e6d]" /> : <ChevronDown className="h-4 w-4 text-[#8a7e6d]" />}
      </button>
      {expanded && (
        <div className="px-4 py-2 divide-y">
          {actions.map((a, i) => (
            <div key={i} className="py-1.5 flex items-center gap-3 text-sm">
              <span className={cn(
                'h-2 w-2 rounded-full shrink-0',
                a.data_found ? 'bg-[#3a7d44]' : 'bg-[#d9cebb]',
              )} />
              <span className="font-mono text-xs min-w-[180px]">{a.tool_name}</span>
              <span className="text-xs text-[#8a7e6d] flex-1 truncate">{a.result_summary || (a.data_found ? 'Found data' : 'No data')}</span>
              {a.latency_ms != null && (
                <span className="text-[10px] text-[#8a7e6d]">{a.latency_ms}ms</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────
export function ResearchReview() {
  useEffect(() => { document.title = 'Research Review - The Organizer' }, [])

  const [reviewStatus, setReviewStatus] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [page, setPage] = useState(1)
  const [view, setView] = useState('queue') // 'queue' | 'stats'
  const [selectedRunId, setSelectedRunId] = useState(null)

  const statsQuery = useGoldReviewStats()
  const queueQuery = useGoldReviewQueue({
    review_status: reviewStatus || undefined,
    q: searchQ || undefined,
    page,
    limit: PAGE_SIZE,
  })

  const stats = statsQuery.data
  const queue = queueQuery.data
  const totalPages = queue?.pages || 0

  // Auto-select first run if none selected
  useEffect(() => {
    if (!selectedRunId && queue?.results?.length > 0) {
      setSelectedRunId(queue.results[0].id)
    }
  }, [queue?.results, selectedRunId])

  // Fetch result + section reviews for selected run
  const resultQuery = useResearchResult(selectedRunId, { enabled: !!selectedRunId })
  const sectionReviewsQuery = useSectionReviews(selectedRunId, { enabled: !!selectedRunId })
  const submitReview = useSubmitSectionReview()
  const markGold = useMarkGoldStandard()
  const unmarkGold = useUnmarkGoldStandard()

  const result = resultQuery.data
  const sectionReviews = sectionReviewsQuery.data?.reviews || []

  // Build review lookup
  const reviewBySection = {}
  for (const r of sectionReviews) {
    reviewBySection[r.section_name] = r
  }

  const dossierSections = result?.dossier?.dossier || result?.dossier || {}

  // Find the selected run in the queue for metadata
  const selectedRun = queue?.results?.find(r => r.id === selectedRunId)

  function handleSubmitReview({ section, review_action, reviewer_notes }) {
    submitReview.mutate({
      runId: selectedRunId,
      section,
      review_action,
      reviewer_notes,
    })
  }

  function handleMarkGold() {
    markGold.mutate({ runId: selectedRunId })
  }

  function handleUnmarkGold() {
    unmarkGold.mutate({ runId: selectedRunId })
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-editorial text-3xl font-bold">Research Report Review</h1>
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
            <BarChart3 className="h-4 w-4" /> Gold Stats
          </button>
        </div>
      </div>

      <StatsBar stats={stats} />

      {/* Stats view */}
      {view === 'stats' && stats && (
        <div className="border rounded-lg overflow-hidden">
          <div className="px-4 py-2.5 bg-muted/30 border-b">
            <h3 className="font-medium">Section Review Breakdown</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/10">
                  <th className="text-left px-3 py-2 font-medium">Section</th>
                  <th className="text-right px-3 py-2 font-medium">Total</th>
                  <th className="text-right px-3 py-2 font-medium text-green-700">Approved</th>
                  <th className="text-right px-3 py-2 font-medium text-red-700">Rejected</th>
                  <th className="text-right px-3 py-2 font-medium text-blue-700">Corrected</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {SECTION_ORDER.map(sn => {
                  const s = stats.by_section?.[sn]
                  const meta = SECTION_META[sn]
                  return (
                    <tr key={sn} className="hover:bg-muted/10">
                      <td className="px-3 py-2 flex items-center gap-2">
                        {meta?.icon && <meta.icon className="h-3.5 w-3.5 text-[#8a7e6d]" />}
                        <span className="text-sm">{meta?.label || sn}</span>
                      </td>
                      <td className="px-3 py-2 text-right">{s?.total || 0}</td>
                      <td className="px-3 py-2 text-right text-green-700">{s?.approve || 0}</td>
                      <td className="px-3 py-2 text-right text-red-700">{s?.reject || 0}</td>
                      <td className="px-3 py-2 text-right text-blue-700">{s?.correct || 0}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Queue view */}
      {view === 'queue' && (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          {/* Sidebar */}
          <div className="space-y-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#8a7e6d]" />
              <input
                type="text"
                value={searchQ}
                onChange={e => { setSearchQ(e.target.value); setPage(1) }}
                placeholder="Search companies..."
                className="w-full rounded border pl-8 pr-2 py-1.5 text-sm bg-transparent"
              />
            </div>

            {/* Filters */}
            <div className="border rounded-lg p-3 space-y-2">
              <h3 className="text-sm font-medium flex items-center gap-1.5">
                <Filter className="h-3.5 w-3.5 text-[#8a7e6d]" /> Filters
              </h3>
              <div>
                <label className="block text-xs text-[#8a7e6d] mb-0.5">Review Status</label>
                <select
                  value={reviewStatus}
                  onChange={e => { setReviewStatus(e.target.value); setPage(1); setSelectedRunId(null) }}
                  className="w-full rounded border px-2 py-1 text-sm bg-transparent"
                >
                  <option value="">All completed</option>
                  <option value="unreviewed">Unreviewed</option>
                  <option value="partial">In Progress</option>
                  <option value="complete">Fully Reviewed</option>
                  <option value="gold">Gold Standard</option>
                </select>
              </div>
            </div>

            <RunSidebar
              runs={queue?.results}
              selectedRunId={selectedRunId}
              onSelectRun={setSelectedRunId}
            />

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between">
                <p className="text-xs text-[#8a7e6d]">Page {page}/{totalPages}</p>
                <div className="flex gap-1">
                  <button type="button" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                    className="p-1 rounded border disabled:opacity-30 hover:bg-muted/30">
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                    className="p-1 rounded border disabled:opacity-30 hover:bg-muted/30">
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Main review area */}
          <div className="space-y-3">
            {/* No run selected */}
            {!selectedRunId && (
              <div className="py-12 text-center">
                <FileText className="h-12 w-12 text-[#8a7e6d]/30 mx-auto mb-3" />
                <h3 className="font-editorial text-lg font-semibold mb-1">Select a run to review</h3>
                <p className="text-sm text-[#8a7e6d]">Choose a research run from the sidebar to begin reviewing.</p>
              </div>
            )}

            {/* Loading */}
            {selectedRunId && resultQuery.isLoading && (
              <div className="text-sm text-[#8a7e6d] py-8 text-center">Loading report...</div>
            )}

            {/* Error */}
            {selectedRunId && resultQuery.isError && (
              <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 text-sm text-destructive flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                Failed to load: {resultQuery.error?.message || 'Unknown error'}
              </div>
            )}

            {/* Run header + sections */}
            {selectedRunId && result && (
              <>
                {/* Run header */}
                <div className="border rounded-lg p-4 bg-card">
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="font-editorial text-xl font-bold flex items-center gap-2">
                        {selectedRun?.is_gold_standard && (
                          <Star className="h-5 w-5 text-[#c78c4e] fill-[#c78c4e]" />
                        )}
                        {result.company_name}
                      </h2>
                      <div className="flex items-center gap-3 mt-1 text-sm text-[#8a7e6d]">
                        <span>Quality: <span className={cn('font-medium', qualityColor(result.quality_score))}>{result.quality_score?.toFixed(1) || '-'}/10</span></span>
                        <span>{result.total_facts} facts</span>
                        <span>{result.sections_filled}/10 sections</span>
                        <span>{sectionReviews.length}/10 reviewed</span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Link
                        to={`/research/${selectedRunId}`}
                        className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium border hover:bg-muted/30 transition-colors"
                      >
                        View Full Report
                      </Link>
                      {selectedRun?.is_gold_standard ? (
                        <button
                          type="button"
                          onClick={handleUnmarkGold}
                          disabled={unmarkGold.isPending}
                          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium bg-[#c78c4e]/15 text-[#c78c4e] border border-[#c78c4e]/30 hover:bg-[#c78c4e]/25 transition-colors disabled:opacity-50"
                        >
                          <Star className="h-3 w-3 fill-current" /> Remove Gold
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleMarkGold}
                          disabled={markGold.isPending}
                          className="inline-flex items-center gap-1 rounded px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                          style={{ backgroundColor: '#c78c4e' }}
                        >
                          <Award className="h-3 w-3" /> Mark Gold Standard
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Section review cards */}
                {SECTION_ORDER.map(sectionKey => (
                  <SectionReviewCard
                    key={sectionKey}
                    sectionKey={sectionKey}
                    narrative={dossierSections[sectionKey]}
                    facts={result.facts_by_section?.[sectionKey] || []}
                    existingReview={reviewBySection[sectionKey]}
                    onSubmitReview={handleSubmitReview}
                    isPending={submitReview.isPending}
                  />
                ))}

                {/* Tool calls */}
                <CompactActionLog actions={result.action_log} />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
