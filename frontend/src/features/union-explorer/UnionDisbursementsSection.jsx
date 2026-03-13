import { DollarSign, AlertTriangle, Shield } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Badge } from '@/components/ui/badge'

const CATEGORY_COLORS = {
  organizing: { bg: 'bg-blue-500', label: 'Organizing' },
  compensation: { bg: 'bg-amber-500', label: 'Compensation' },
  benefits_members: { bg: 'bg-green-500', label: 'Benefits' },
  administration: { bg: 'bg-gray-500', label: 'Administration' },
  external: { bg: 'bg-purple-500', label: 'External' },
}

function formatCurrency(n) {
  if (n == null || n === 0) return '$0'
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return '$' + (n / 1_000_000).toFixed(1) + 'M'
  if (abs >= 1_000) return '$' + (n / 1_000).toFixed(1) + 'K'
  return '$' + Number(n).toLocaleString()
}

/**
 * Spending breakdown section for union profile.
 * Shows categorized disbursements as stacked bar + year-over-year table.
 */
export function UnionDisbursementsSection({ data, isLoading }) {
  if (isLoading) return null
  if (!data || !data.years || data.years.length === 0) {
    return (
      <CollapsibleCard icon={DollarSign} title="Spending Breakdown" defaultOpen={false}>
        <p className="text-sm text-muted-foreground">No disbursement data available.</p>
      </CollapsibleCard>
    )
  }

  const latest = data.years[0]
  const total = latest.total || 1

  const compPct = total > 0 ? (latest.compensation / total) * 100 : 0
  const highComp = compPct > 25

  const segments = ['organizing', 'compensation', 'benefits_members', 'administration', 'external']
  const barSegments = segments
    .map((key) => ({
      key,
      value: latest[key] || 0,
      pct: total > 0 ? ((latest[key] || 0) / total) * 100 : 0,
      ...CATEGORY_COLORS[key],
    }))
    .filter((s) => s.pct > 0)

  return (
    <CollapsibleCard
      icon={DollarSign}
      title="Spending Breakdown"
      summary={formatCurrency(latest.total) + ' total'}
      defaultOpen={false}
    >
      {/* Badges */}
      <div className="flex flex-wrap gap-2 mb-4">
        {data.has_strike_fund ? (
          <Badge className="bg-green-100 text-green-800">
            <Shield className="h-3 w-3 mr-1" />
            Has Strike Fund
          </Badge>
        ) : (
          <Badge className="bg-amber-100 text-amber-800">
            <Shield className="h-3 w-3 mr-1" />
            No Strike Fund
          </Badge>
        )}
        {highComp && (
          <Badge className="bg-amber-100 text-amber-800">
            <AlertTriangle className="h-3 w-3 mr-1" />
            High Officer Comp ({compPct.toFixed(1)}%)
          </Badge>
        )}
      </div>

      {/* Stacked horizontal bar */}
      <div className="mb-2">
        <div className="flex h-6 w-full rounded overflow-hidden">
          {barSegments.map((seg) => (
            <div
              key={seg.key}
              className={seg.bg}
              style={{ width: seg.pct.toFixed(1) + '%' }}
              title={seg.label + ': ' + seg.pct.toFixed(1) + '%'}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-muted-foreground">
          {barSegments.map((seg) => (
            <span key={seg.key} className="flex items-center gap-1">
              <span className={'inline-block w-2.5 h-2.5 rounded-sm ' + seg.bg} />
              {seg.label} {seg.pct.toFixed(1)}%
            </span>
          ))}
        </div>
      </div>

      {/* Year-over-year table */}
      <div className="overflow-x-auto border mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Year</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Organizing</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Compensation</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Benefits</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Admin</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">External</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.years.map((yr) => (
              <tr key={yr.year} className="border-b">
                <td className="px-3 py-2 tabular-nums font-medium">{yr.year}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(yr.organizing)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(yr.compensation)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(yr.benefits_members)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(yr.administration)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(yr.external)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{formatCurrency(yr.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CollapsibleCard>
  )
}
