import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const FACTORS = [
  { key: 'score_nlrb', label: 'NLRB Activity' },
  { key: 'score_osha', label: 'OSHA Safety' },
  { key: 'score_whd', label: 'Wage & Hour' },
  { key: 'score_contracts', label: 'Gov Contracts' },
  { key: 'score_union_proximity', label: 'Union Proximity' },
  { key: 'score_financial', label: 'Financial' },
  { key: 'score_size', label: 'Employer Size' },
  { key: 'score_similarity', label: 'Peer Similarity' },
  { key: 'score_industry_growth', label: 'Industry Growth' },
]

function getBarColor(value) {
  if (value >= 7) return 'bg-red-600'
  if (value >= 4) return 'bg-orange-500'
  return 'bg-stone-400'
}

function ScoreBar({ label, value, explanation }) {
  const hasValue = value != null
  const displayValue = hasValue ? Number(value).toFixed(1) : null
  const widthPct = hasValue ? Math.min((value / 10) * 100, 100) : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className={cn('text-xs', hasValue ? 'text-foreground' : 'text-muted-foreground')}>
          {hasValue ? displayValue : 'No data'}
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

  const factorsWithData = FACTORS.filter(f => scorecard[f.key] != null)
  const coverage = Math.round((factorsWithData.length / FACTORS.length) * 100)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organizing Scorecard</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {FACTORS.map(({ key, label }) => (
            <ScoreBar
              key={key}
              label={label}
              value={scorecard[key]}
              explanation={explanations?.[key]}
            />
          ))}
        </div>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          {factorsWithData.length} of {FACTORS.length} factors available ({coverage}% coverage)
        </p>
      </CardFooter>
    </Card>
  )
}
