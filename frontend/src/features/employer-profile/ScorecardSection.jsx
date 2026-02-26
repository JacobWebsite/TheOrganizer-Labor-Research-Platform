import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
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
  if (value >= 7) return 'bg-red-600'
  if (value >= 4) return 'bg-red-400'
  return 'bg-red-200'
}

function ScoreBar({ label, weight, value, explanation, disabled, filter }) {
  if (disabled) {
    return (
      <div className="space-y-1 opacity-50">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">{label}</span>
          <span className="text-xs text-muted-foreground italic">Under Development</span>
        </div>
        <div className="h-2 w-full bg-muted overflow-hidden" />
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
        <span className={cn('text-xs', hasValue ? 'text-foreground' : 'text-muted-foreground')}>
          {hasValue ? displayValue : '\u2014'}
        </span>
      </div>
      <div className="h-2 w-full bg-muted overflow-hidden">
        {hasValue && (
          <div
            className={cn('h-full transition-all', getBarColor(value))}
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

export function ScorecardSection({ scorecard, explanations }) {
  if (!scorecard) return null

  const activeFactors = FACTORS.filter(f => !f.disabled)
  const factorsWithData = activeFactors.filter(f => scorecard[f.key] != null)
  const coverage = Math.round((factorsWithData.length / ACTIVE_FACTOR_COUNT) * 100)

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
            />
          ))}
        </div>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          {factorsWithData.length} of {ACTIVE_FACTOR_COUNT} factors available ({coverage}% coverage)
        </p>
      </CardFooter>
    </Card>
  )
}
