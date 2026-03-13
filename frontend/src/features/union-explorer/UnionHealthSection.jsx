import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const GRADE_COLORS = {
  A: '#1a6b5a',
  B: '#4a90a4',
  C: '#c78c4e',
  D: '#b8860b',
  F: '#a0522d',
}

function IndicatorBar({ label, indicator }) {
  if (!indicator) {
    return (
      <div className="space-y-1">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">{label}</span>
          <span className="text-xs text-muted-foreground">No data</span>
        </div>
        <div className="h-2 bg-muted rounded-full" />
      </div>
    )
  }

  const pct = Math.max(0, Math.min(100, indicator.score))
  const color = pct >= 70 ? '#1a6b5a' : pct >= 40 ? '#c78c4e' : '#a0522d'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-xs text-muted-foreground">{indicator.label} ({Math.round(pct)})</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

export function UnionHealthSection({ data, isLoading }) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-5 w-32" /></CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-8 w-full" />)}
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const grade = data.composite?.grade || '?'
  const gradeColor = GRADE_COLORS[grade] || '#8a7e6d'

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base font-editorial">Union Health</CardTitle>
        <div
          className="flex items-center justify-center w-10 h-10 rounded-full text-white font-bold text-lg"
          style={{ backgroundColor: gradeColor }}
          title={`Composite score: ${data.composite?.score ?? '?'}`}
        >
          {grade}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <IndicatorBar label="Membership Trend" indicator={data.membership_trend} />
        <IndicatorBar label="Election Win Rate" indicator={data.election_win_rate} />
        <IndicatorBar label="Financial Stability" indicator={data.financial_stability} />
        <IndicatorBar label="Organizing Activity" indicator={data.organizing_activity} />
        <p className="text-xs text-muted-foreground pt-1">
          Based on {data.composite?.indicators_available ?? 0} of 4 indicators
        </p>
      </CardContent>
    </Card>
  )
}
