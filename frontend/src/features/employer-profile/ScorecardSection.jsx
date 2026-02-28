import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'
import { cn } from '@/lib/utils'

const FACTORS = [
  { key: 'score_union_proximity', label: 'Union Proximity', weight: '3x' },
  { key: 'score_size', label: 'Employer Size', weight: null, filter: true },
  { key: 'score_nlrb', label: 'NLRB Activity', weight: '3x' },
  { key: 'score_contracts', label: 'Gov Contracts', weight: '2x' },
  { key: 'score_industry_growth', label: 'Industry Growth', weight: '2x' },
  { key: 'score_similarity', label: 'Peer Similarity', weight: null, disabled: true },
  { key: 'score_osha', label: 'OSHA Safety', weight: '1x' },
  { key: 'score_whd', label: 'Wage & Hour', weight: '1x' },
  { key: 'score_financial', label: 'Financial', weight: '2x' },
]

const ACTIVE_FACTOR_COUNT = FACTORS.filter(f => !f.disabled).length

function getBarColor(value) {
  if (value >= 7) return 'bg-[#c23a22]'
  if (value >= 4) return 'bg-[#c78c4e]'
  return 'bg-[#d9cebb]'
}

const FACTOR_SOURCE_MAP = {
  score_osha: 'osha',
  score_nlrb: 'nlrb',
  score_whd: 'whd',
  score_contracts: 'sam',
  score_financial: ['990', 'sec'],
  score_union_proximity: null,
  score_size: null,
  score_industry_growth: null,
  score_similarity: null,
}

function getFactorAttribution(matchSummary, factorKey) {
  if (!matchSummary) return null
  const source = FACTOR_SOURCE_MAP[factorKey]
  if (!source) return null
  if (Array.isArray(source)) {
    // Return whichever has higher confidence
    const entries = source.map(s => matchSummary.find(e => e.source_system === s)).filter(Boolean)
    if (entries.length === 0) return null
    return entries.reduce((best, e) => {
      const bestScore = best.best_confidence_score ?? best.best_confidence ?? 0
      const eScore = e.best_confidence_score ?? e.best_confidence ?? 0
      return eScore > bestScore ? e : best
    })
  }
  return matchSummary.find(e => e.source_system === source) || null
}

function ScoreBar({ label, weight, value, explanation, disabled, filter, enhanced, attribution }) {
  if (disabled) {
    return (
      <div className="space-y-1 opacity-50">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">{label}</span>
          <span className="text-xs text-muted-foreground italic">Under Development</span>
        </div>
        <div className="h-2 w-full bg-muted rounded-full overflow-hidden" />
      </div>
    )
  }

  const hasValue = value != null
  const displayValue = hasValue ? Number(value).toFixed(1) : null
  const widthPct = hasValue ? Math.min((value / 10) * 100, 100) : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">
          {label}
          {weight && <span className="ml-1 text-xs text-muted-foreground">({weight})</span>}
          {filter && <span className="ml-1 text-xs text-muted-foreground italic">(filter only)</span>}
        </span>
        <span className="flex items-center gap-1">
          {enhanced && <span className="text-[10px] text-[#3a7d44] font-semibold" title="Enhanced by web research">R</span>}
          {attribution && hasValue && (
            <ConfidenceDots
              confidence={attribution.best_confidence_score != null ? attribution.best_confidence_score : attribution.best_confidence}
              matchTier={attribution.best_match_tier}
              className="mr-1"
            />
          )}
          <span className={cn('text-xs', hasValue ? 'text-foreground' : 'text-muted-foreground')}>
            {hasValue ? displayValue : '\u2014'}
          </span>
        </span>
      </div>
      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
        {hasValue && (
          <div
            className={cn('h-full rounded-full transition-all', getBarColor(value))}
            style={{ width: `${widthPct}%` }}
          />
        )}
      </div>
      {explanation && (
        <p className="text-xs text-muted-foreground">{explanation}</p>
      )}
    </div>
  )
}

const FACTOR_ENH_MAP = {
  score_osha: 'enh_score_osha',
  score_nlrb: 'enh_score_nlrb',
  score_whd: 'enh_score_whd',
  score_contracts: 'enh_score_contracts',
  score_financial: 'enh_score_financial',
  score_size: 'enh_score_size',
}

export function ScorecardSection({ scorecard, explanations, scorecardDetail, matchSummary }) {
  if (!scorecard) return null

  const activeFactors = FACTORS.filter(f => !f.disabled)
  const factorsWithData = activeFactors.filter(f => scorecard[f.key] != null)
  const coverage = Math.round((factorsWithData.length / ACTIVE_FACTOR_COUNT) * 100)

  // Detect which factors were enhanced by research
  const detail = scorecardDetail || {}
  function isEnhanced(key) {
    const enhKey = FACTOR_ENH_MAP[key]
    if (!enhKey || !detail.has_research) return false
    const base = scorecard[key]
    const enh = detail[enhKey]
    return base != null && enh != null && enh > base
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organizing Scorecard</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {FACTORS.map(({ key, label, weight, disabled, filter }) => (
            <ScoreBar
              key={key}
              label={label}
              weight={weight}
              value={scorecard[key]}
              explanation={explanations?.[key]}
              disabled={disabled}
              filter={filter}
              enhanced={isEnhanced(key)}
              attribution={getFactorAttribution(matchSummary, key)}
            />
          ))}
        </div>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          {factorsWithData.length} of {ACTIVE_FACTOR_COUNT} factors available ({coverage}% coverage)
          {detail.has_research && (
            <span className="ml-1">
              -- <span className="text-[#3a7d44] font-medium">R</span> = enhanced by web research
            </span>
          )}
        </p>
      </CardFooter>
    </Card>
  )
}
