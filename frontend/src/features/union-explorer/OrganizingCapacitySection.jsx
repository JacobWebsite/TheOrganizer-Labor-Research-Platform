import { TrendingUp, TrendingDown, Minus, DollarSign, PieChart } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

const TREND_CONFIG = {
  increasing: { label: 'Increasing', icon: TrendingUp, color: 'bg-green-100 text-green-800' },
  decreasing: { label: 'Decreasing', icon: TrendingDown, color: 'bg-red-100 text-red-800' },
  stable: { label: 'Stable', icon: Minus, color: 'bg-gray-100 text-gray-800' },
}

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return '$' + Number(n).toLocaleString()
}

function formatPercent(n) {
  if (n == null) return '\u2014'
  return (n * 100).toFixed(1) + '%'
}

/**
 * Organizing capacity metrics: spend share, total disbursements, trend.
 */
export function OrganizingCapacitySection({ data }) {
  if (!data) return null

  const trend = data.trend ? TREND_CONFIG[data.trend.toLowerCase()] || TREND_CONFIG.stable : null

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Representational Spend</CardTitle>
          {trend && (
            <Badge className={trend.color}>
              <trend.icon className="h-3 w-3 mr-1" />
              {trend.label}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4">
          Percentage of total spending devoted to representational activities (contract negotiation, grievance handling, arbitration) and strike support. Does not include political spending.
        </p>
        <div className="flex flex-wrap gap-x-10 gap-y-3">
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <PieChart className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Organizing spend share</span>
            </div>
            <p className="text-2xl font-bold tabular-nums">
              {formatPercent(data.organizing_spend_share)}
            </p>
          </div>
          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <DollarSign className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Total disbursements</span>
            </div>
            <p className="text-2xl font-bold tabular-nums">
              {formatCurrency(data.total_disbursements)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
