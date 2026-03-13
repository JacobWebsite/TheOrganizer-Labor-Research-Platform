import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Plus, Radar, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PageSkeleton } from '@/shared/components/PageSkeleton'
import { parseCanonicalId, useScorecardDetail } from '@/shared/api/profile'
import { useNonUnionTargets, useTargetScorecardDetail } from '@/shared/api/targets'
import { cn } from '@/lib/utils'

const MAX_COMPARE = 3
const FACTORS = [
  { key: 'score_osha', label: 'OSHA' },
  { key: 'score_nlrb', label: 'NLRB' },
  { key: 'score_whd', label: 'WHD' },
  { key: 'score_contracts', label: 'Contracts' },
  { key: 'score_financial', label: 'Financial' },
  { key: 'score_industry_growth', label: 'Industry Growth' },
  { key: 'score_union_proximity', label: 'Union Proximity' },
  { key: 'score_similarity', label: 'Similarity' },
  { key: 'score_size', label: 'Size' },
]
const SLOT_COLORS = ['#3a6b8c', '#c78c4e', '#3a7d44']

function parseIds(searchParams) {
  return (searchParams.get('ids') || '')
    .split(',')
    .map((id) => id.trim())
    .filter(Boolean)
    .filter((id, index, list) => list.indexOf(id) === index)
    .slice(0, MAX_COMPARE)
}

function formatScore(value) {
  if (value == null) return '-'
  return Number(value).toFixed(1)
}

function normalizeEmployer(data, parsedId) {
  if (!data) return null
  if (parsedId.sourceType === 'MASTER') {
    const scorecard = data.scorecard || {}
    const summary = data.summary || {}
    return {
      employer_id: `MASTER-${scorecard.master_id || parsedId.rawId}`,
      employer_name: scorecard.display_name,
      state: scorecard.state,
      naics: scorecard.naics,
      weighted_score: summary.signals_present ?? scorecard.signals_present,
      score_tier: summary.gold_standard_tier || scorecard.gold_standard_tier,
      factors_available: summary.signals_present ?? scorecard.signals_present,
      score_osha: scorecard.signal_osha,
      score_nlrb: scorecard.signal_nlrb,
      score_whd: scorecard.signal_whd,
      score_contracts: scorecard.signal_contracts,
      score_financial: scorecard.signal_financial,
      score_industry_growth: scorecard.signal_industry_growth,
      score_union_proximity: scorecard.signal_union_density,
      score_similarity: scorecard.signal_similarity,
      score_size: scorecard.signal_size,
    }
  }
  return data
}

function polarPoint(cx, cy, radius, index, total) {
  const angle = ((Math.PI * 2) / total) * index - Math.PI / 2
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  }
}

function buildPolygonPoints(values, radius, cx, cy) {
  return values.map((value, index) => {
    const point = polarPoint(cx, cy, radius * (Math.max(0, Math.min(10, value || 0)) / 10), index, values.length)
    return `${point.x},${point.y}`
  }).join(' ')
}

function RadarChartSvg({ employers }) {
  const size = 420
  const cx = size / 2
  const cy = size / 2
  const radius = 140

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[420px] mx-auto">
      {[0.25, 0.5, 0.75, 1].map((level) => (
        <polygon
          key={level}
          points={FACTORS.map((_, index) => {
            const point = polarPoint(cx, cy, radius * level, index, FACTORS.length)
            return `${point.x},${point.y}`
          }).join(' ')}
          fill="none"
          stroke="#d9cebb"
          strokeWidth="1"
        />
      ))}
      {FACTORS.map((factor, index) => {
        const point = polarPoint(cx, cy, radius, index, FACTORS.length)
        const labelPoint = polarPoint(cx, cy, radius + 28, index, FACTORS.length)
        return (
          <g key={factor.key}>
            <line x1={cx} y1={cy} x2={point.x} y2={point.y} stroke="#d9cebb" strokeWidth="1" />
            <text
              x={labelPoint.x}
              y={labelPoint.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-[#8a7e6b] text-[10px] font-medium"
            >
              {factor.label}
            </text>
          </g>
        )
      })}
      {employers.map((employer, index) => {
        const values = FACTORS.map((factor) => employer?.[factor.key] ?? 0)
        return (
          <polygon
            key={employer.employer_id || employer.employer_name || index}
            points={buildPolygonPoints(values, radius, cx, cy)}
            fill={SLOT_COLORS[index]}
            fillOpacity="0.16"
            stroke={SLOT_COLORS[index]}
            strokeWidth="2.5"
          />
        )
      })}
      <circle cx={cx} cy={cy} r="3" fill="#8a7e6b" />
    </svg>
  )
}

function SlotCard({ slot, color, onRemove }) {
  if (!slot.id) {
    return (
      <Card className="border-dashed border-[#d9cebb] bg-[#f5f0e8]">
        <CardContent className="pt-6 text-center text-sm text-muted-foreground">
          <Plus className="h-5 w-5 mx-auto mb-2" />
          Add employer to compare
        </CardContent>
      </Card>
    )
  }

  if (slot.query.isLoading) {
    return <PageSkeleton />
  }

  if (slot.query.isError) {
    return (
      <Card className="border-[#c23a22]/30">
        <CardContent className="pt-6 text-sm text-[#c23a22]">
          Failed to load employer {slot.id}.
        </CardContent>
      </Card>
    )
  }

  const employer = slot.employer
  if (!employer) return null

  return (
    <Card className="overflow-hidden">
      <div className="h-1.5" style={{ backgroundColor: color }} />
      <CardContent className="pt-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-editorial text-lg font-semibold">{employer.employer_name}</h3>
            <p className="text-sm text-muted-foreground">
              {[employer.state, employer.naics].filter(Boolean).join(' | ') || 'No detail'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onRemove(slot.id)}
            className="text-muted-foreground hover:text-[#c23a22]"
            aria-label={`Remove ${employer.employer_name}`}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-4 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Weighted</p>
            <p className="font-editorial text-2xl font-bold" style={{ color }}>{formatScore(employer.weighted_score)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Tier</p>
            <p className="font-medium">{employer.score_tier || '-'}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Factors</p>
            <p className="font-medium">{employer.factors_available ?? '-'}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function SearchPanel({ ids, onAdd }) {
  const [query, setQuery] = useState('')
  const searchQuery = useNonUnionTargets({
    q: query.trim() || undefined,
    limit: 8,
    enabled: query.trim().length >= 2,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          Add Employers
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="block">
          <span className="sr-only">Search employers</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search non-union targets by employer name"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        </label>
        {query.trim().length < 2 && (
          <p className="text-sm text-muted-foreground">Search by name to add up to three employers.</p>
        )}
        {searchQuery.isLoading && <p className="text-sm text-muted-foreground">Searching...</p>}
        {searchQuery.data?.results?.length > 0 && (
          <div className="space-y-2">
            {searchQuery.data.results.map((employer) => {
              const id = `MASTER-${employer.id}`
              const isSelected = ids.includes(id)
              const atLimit = !isSelected && ids.length >= MAX_COMPARE
              return (
                <div key={id} className="flex items-center justify-between rounded-md border bg-card px-3 py-2">
                  <div>
                    <p className="font-medium">{employer.display_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {[employer.city, employer.state, employer.naics].filter(Boolean).join(' | ')}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant={isSelected ? 'secondary' : 'outline'}
                    size="sm"
                    disabled={atLimit}
                    onClick={() => onAdd(id)}
                  >
                    {isSelected ? 'Added' : 'Add'}
                  </Button>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function CompareEmployersPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const ids = parseIds(searchParams)

  const slotIds = [ids[0], ids[1], ids[2]]
  const parsedSlots = slotIds.map((id) => parseCanonicalId(id))
  const f7Queries = [
    useScorecardDetail(parsedSlots[0].isF7 ? parsedSlots[0].rawId : null, { enabled: parsedSlots[0].isF7 && !!slotIds[0] }),
    useScorecardDetail(parsedSlots[1].isF7 ? parsedSlots[1].rawId : null, { enabled: parsedSlots[1].isF7 && !!slotIds[1] }),
    useScorecardDetail(parsedSlots[2].isF7 ? parsedSlots[2].rawId : null, { enabled: parsedSlots[2].isF7 && !!slotIds[2] }),
  ]
  const masterQueries = [
    useTargetScorecardDetail(parsedSlots[0].sourceType === 'MASTER' ? parsedSlots[0].rawId : null, { enabled: parsedSlots[0].sourceType === 'MASTER' && !!slotIds[0] }),
    useTargetScorecardDetail(parsedSlots[1].sourceType === 'MASTER' ? parsedSlots[1].rawId : null, { enabled: parsedSlots[1].sourceType === 'MASTER' && !!slotIds[1] }),
    useTargetScorecardDetail(parsedSlots[2].sourceType === 'MASTER' ? parsedSlots[2].rawId : null, { enabled: parsedSlots[2].sourceType === 'MASTER' && !!slotIds[2] }),
  ]

  const slots = slotIds.map((id, index) => {
    const parsedId = parsedSlots[index]
    const query = parsedId.sourceType === 'MASTER' ? masterQueries[index] : f7Queries[index]
    return {
      id,
      parsedId,
      query,
      employer: normalizeEmployer(query.data, parsedId),
    }
  })
  const employers = slots.map((slot) => slot.employer).filter(Boolean)
  const isLoading = slots.some((slot) => slot.id && slot.query.isLoading)
  const hasAnyIds = ids.length > 0

  function updateIds(nextIds) {
    const normalized = nextIds.slice(0, MAX_COMPARE)
    if (normalized.length === 0) {
      setSearchParams({})
      return
    }
    setSearchParams({ ids: normalized.join(',') })
  }

  function addEmployer(id) {
    if (ids.includes(id) || ids.length >= MAX_COMPARE) return
    updateIds([...ids, id])
  }

  function removeEmployer(id) {
    updateIds(ids.filter((candidate) => candidate !== id))
  }

  const metricRows = useMemo(() => ([
    { label: 'Employer Name', render: (employer) => employer?.employer_name || '-' },
    { label: 'State', render: (employer) => employer?.state || '-' },
    { label: 'NAICS', render: (employer) => employer?.naics || '-' },
    { label: 'Weighted Score', render: (employer) => formatScore(employer?.weighted_score) },
    { label: 'Score Tier', render: (employer) => employer?.score_tier || '-' },
    { label: 'Factors Available', render: (employer) => employer?.factors_available ?? '-' },
    ...FACTORS.map((factor) => ({
      label: factor.label,
      render: (employer) => formatScore(employer?.[factor.key]),
    })),
  ]), [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <h1 className="font-editorial text-[32px] font-bold mt-2">Employer Comparison</h1>
          <p className="text-sm text-muted-foreground">Compare up to three employers across scorecard factors.</p>
        </div>
        {hasAnyIds && (
          <Button variant="outline" size="sm" onClick={() => updateIds([])}>
            Clear Compare
          </Button>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden bg-[linear-gradient(135deg,rgba(58,107,140,0.08),rgba(245,240,232,0.95)_42%,rgba(199,140,78,0.10))]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Radar className="h-4 w-4 text-muted-foreground" />
              Score Factor Radar
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading && <PageSkeleton />}
            {!isLoading && employers.length > 0 && (
              <>
                <RadarChartSvg employers={employers} />
                <div className="flex flex-wrap justify-center gap-3 mt-4">
                  {employers.map((employer, index) => (
                    <div key={employer.employer_id || employer.employer_name} className="inline-flex items-center gap-2 text-sm">
                      <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: SLOT_COLORS[index] }} />
                      <span>{employer.employer_name}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {!isLoading && employers.length === 0 && (
              <div className="py-14 text-center text-sm text-muted-foreground">
                Add employers to build a side-by-side comparison.
              </div>
            )}
          </CardContent>
        </Card>

        <SearchPanel ids={ids} onAdd={addEmployer} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {slots.map((slot, index) => (
          <SlotCard
            key={slot.id || `slot-${index}`}
            slot={slot}
            color={SLOT_COLORS[index]}
            onRemove={removeEmployer}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Comparison Table</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b bg-[#ede7db]">
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">Metric</th>
                {slots.map((slot, index) => (
                  <th key={slot.id || `head-${index}`} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold',
                        !slot.id && 'bg-muted text-muted-foreground'
                      )}
                      style={slot.id ? { backgroundColor: `${SLOT_COLORS[index]}22`, color: SLOT_COLORS[index] } : undefined}
                    >
                      {slot.employer?.employer_name || `Slot ${index + 1}`}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metricRows.map((row) => (
                <tr key={row.label} className="border-b last:border-b-0">
                  <td className="px-3 py-2 font-medium">{row.label}</td>
                  {slots.map((slot, index) => (
                    <td key={`${row.label}-${slot.id || index}`} className="px-3 py-2 text-muted-foreground">
                      {slot.query.isLoading ? 'Loading...' : row.render(slot.employer)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}
