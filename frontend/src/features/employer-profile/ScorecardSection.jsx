import { AlertTriangle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { ScoreGauge } from '@/shared/components/ScoreGauge'
import { ConfidenceDots } from '@/shared/components/ConfidenceDots'

const FACTORS = [
  { key: 'score_osha', label: 'OSHA Safety', weight: 'Anger', direct: true },
  { key: 'score_whd', label: 'Wage & Hour', weight: 'Anger', direct: true },
  { key: 'score_nlrb', label: 'NLRB Activity', weight: 'Anger', direct: true },
  { key: 'score_contracts', label: 'Gov Contracts', weight: 'Leverage', direct: true },
  { key: 'score_financial', label: 'Financial', weight: 'Leverage', direct: true },
  { key: 'score_union_proximity', label: 'Union Proximity', weight: 'Leverage' },
  { key: 'score_industry_growth', label: 'Industry Growth', weight: 'Leverage' },
  { key: 'score_similarity', label: 'Peer Similarity', weight: 'Leverage' },
  { key: 'score_size', label: 'Employer Size', weight: null, filter: true },
]

const DIRECT_FACTOR_COUNT = FACTORS.filter(f => f.direct).length

const ACTIVE_FACTOR_COUNT = FACTORS.filter(f => !f.disabled).length

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
  const directFactorsWithData = activeFactors.filter(f => f.direct && scorecard[f.key] != null).length
  const scorableCoverage = Math.round((directFactorsWithData / DIRECT_FACTOR_COUNT) * 100)
  const hasThinData = scorecardDetail?.has_thin_data === true

  // Detect which factors were enhanced by research
  const detail = scorecardDetail || {}
  function isEnhanced(key) {
    const enhKey = FACTOR_ENH_MAP[key]
    if (!enhKey || !detail.has_research) return false
    const base = scorecard[key]
    const enh = detail[enhKey]
    return base != null && enh != null && enh > base
  }
  function isVerified(key) {
    const enhKey = FACTOR_ENH_MAP[key]
    if (!enhKey || !detail.has_research) return false
    const base = scorecard[key]
    const enh = detail[enhKey]
    return base != null && enh != null && enh === base
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organizing Scorecard</CardTitle>
      </CardHeader>
      <CardContent>
        {hasThinData && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <div>
              <span className="font-semibold">Thin data:</span> this score comes from modeled
              signals (similarity, industry, proximity) rather than direct employer records.
              No OSHA, NLRB, WHD, contract, or financial filings were matched to this employer.
              Treat the score as a starting point, not a verdict.
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-4 justify-center">
          {FACTORS.map(({ key, label, weight, disabled, filter }) => {
            if (disabled) return null
            const value = scorecard[key]
            const attribution = getFactorAttribution(matchSummary, key)
            const enhanced = isEnhanced(key)
            const verified = isVerified(key)

            return (
              <div key={key} className="flex flex-col items-center gap-1 min-w-[80px]">
                <ScoreGauge value={value} label={label} size={64} />
                <div className="flex items-center gap-1">
                  {enhanced && <span className="text-[10px] text-[#3a7d44] font-semibold" title="Enhanced by web research">R</span>}
                  {verified && <span className="text-[10px] text-[#3a6b8c] font-semibold" title="Verified by web research">V</span>}
                  {attribution && value != null && (
                    <ConfidenceDots
                      confidence={attribution.best_confidence_score != null ? attribution.best_confidence_score : attribution.best_confidence}
                      matchTier={attribution.best_match_tier}
                    />
                  )}
                </div>
                {weight && <span className="text-[10px] text-[#8a7e6d]">({weight})</span>}
                {filter && <span className="text-[10px] text-[#8a7e6d] italic">(filter)</span>}
                {explanations?.[key] && (
                  <p className="text-[10px] text-[#8a7e6d] text-center max-w-[120px] leading-tight">{explanations[key]}</p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
      <CardFooter>
        <div className="text-xs text-muted-foreground space-y-0.5">
          <p>
            <span className="font-medium">Direct evidence:</span>{' '}
            {directFactorsWithData} of {DIRECT_FACTOR_COUNT} factors ({scorableCoverage}%) --
            employer-specific records (OSHA, NLRB, WHD, contracts, financial)
          </p>
          <p>
            <span className="font-medium">Total coverage:</span>{' '}
            {factorsWithData.length} of {ACTIVE_FACTOR_COUNT} factors ({coverage}%) --
            includes modeled signals (similarity, proximity, industry, size)
          </p>
          {detail.has_research && (
            <p>
              <span className="text-[#3a7d44] font-medium">R</span> = enhanced by web research
            </p>
          )}
        </div>
      </CardFooter>
    </Card>
  )
}
