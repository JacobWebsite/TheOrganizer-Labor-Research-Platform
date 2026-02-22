import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

const TREND_CONFIG = {
  growing: { label: 'Growing', icon: TrendingUp, color: 'bg-green-100 text-green-800' },
  declining: { label: 'Declining', icon: TrendingDown, color: 'bg-red-100 text-red-800' },
  stable: { label: 'Stable', icon: Minus, color: 'bg-gray-100 text-gray-800' },
}

/**
 * 10-year membership history rendered as horizontal CSS bars.
 * No chart library required.
 */
export function MembershipSection({ data }) {
  if (!data) return null

  const history = data.history || []
  if (history.length === 0) return null

  const maxMembers = Math.max(...history.map((h) => h.members || 0), 1)
  const trend = data.trend ? TREND_CONFIG[data.trend.toLowerCase()] || TREND_CONFIG.stable : null
  const changePct = data.change_pct
  const peakYear = data.peak_year
  const peakMembers = data.peak_members

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Membership History</CardTitle>
          <div className="flex items-center gap-2">
            {trend && (
              <Badge className={trend.color}>
                <trend.icon className="h-3 w-3 mr-1" />
                {trend.label}
              </Badge>
            )}
            {changePct != null && (
              <span className="text-sm text-muted-foreground">
                {changePct > 0 ? '+' : ''}{changePct.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
        {peakYear && peakMembers != null && (
          <p className="text-xs text-muted-foreground">
            Peak: {peakYear} ({Number(peakMembers).toLocaleString()} members)
          </p>
        )}
      </CardHeader>
      <CardContent>
        <div className="space-y-1.5">
          {history.map((h) => {
            const width = maxMembers > 0 ? ((h.members || 0) / maxMembers) * 100 : 0
            const isPeak = h.year === peakYear
            return (
              <div key={h.year} className="flex items-center gap-3">
                <span className={`w-10 text-xs text-right tabular-nums ${isPeak ? 'font-bold' : 'text-muted-foreground'}`}>
                  {h.year}
                </span>
                <div className="flex-1 h-5 bg-muted overflow-hidden">
                  <div
                    className={`h-full transition-all ${isPeak ? 'bg-primary' : 'bg-primary/70'}`}
                    style={{ width: `${width}%` }}
                  />
                </div>
                <span className={`w-20 text-xs text-right tabular-nums ${isPeak ? 'font-bold' : 'text-muted-foreground'}`}>
                  {(h.members || 0).toLocaleString()}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
