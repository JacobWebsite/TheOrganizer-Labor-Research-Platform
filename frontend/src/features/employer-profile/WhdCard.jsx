import { useState } from 'react'
import { Scale, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { useEmployerWhd } from '@/shared/api/profile'
import { Button } from '@/components/ui/button'

function formatCurrency(n) {
  if (n == null) return '$0'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function WhdCard({ employerId, sourceAttribution }) {
  const { data, isLoading } = useEmployerWhd(employerId)
  const [showAll, setShowAll] = useState(false)

  if (isLoading) return null

  // If no data at all, show warning instead of hiding
  if (!data || (!data.whd_summary && (!data.cases || data.cases.length === 0))) {
    return (
      <CollapsibleCard icon={Scale} title="Wage & Hour (WHD)" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No Wage & Hour Division records have been matched to this employer. This does{' '}
            <strong>not</strong> mean no violations exist — it may mean our matching has not yet
            connected this employer to WHD case records.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data.whd_summary || {}
  const cases = data.cases || []
  const displayCases = showAll ? cases : cases.slice(0, 5)
  const caseCount = summary.case_count || cases.length
  const backwages = summary.total_backwages || 0

  const hasChildLabor = cases.some(c => c.flsa_child_labor_violations > 0)
  const hasRepeatViolator = cases.some(c => c.flsa_repeat_violator)

  return (
    <CollapsibleCard
      icon={Scale}
      title="Wage & Hour (WHD)"
      summary={`${caseCount} cases · ${formatCurrency(backwages)} backwages`}
    >
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        {(hasChildLabor || hasRepeatViolator) && (
          <div className="flex flex-wrap gap-2">
            {hasChildLabor && (
              <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold bg-red-100 text-red-800">
                <AlertTriangle className="h-3 w-3" />
                Child Labor Violation
              </span>
            )}
            {hasRepeatViolator && (
              <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold bg-amber-100 text-amber-800">
                <AlertTriangle className="h-3 w-3" />
                Repeat Violator
              </span>
            )}
          </div>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground">Cases</span>
            <div className="font-medium">{caseCount}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Violations</span>
            <div className="font-medium">{(summary.total_violations || 0).toLocaleString()}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Backwages</span>
            <div className="font-medium">{formatCurrency(backwages)}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Penalties</span>
            <div className="font-medium">{formatCurrency(summary.total_penalties || 0)}</div>
          </div>
        </div>

        {cases.length > 0 && (
          <div className="overflow-x-auto border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-2 py-1.5 text-left font-medium">Trade Name</th>
                  <th className="px-2 py-1.5 text-left font-medium">Location</th>
                  <th className="px-2 py-1.5 text-right font-medium">Violations</th>
                  <th className="px-2 py-1.5 text-right font-medium">Backwages</th>
                </tr>
              </thead>
              <tbody>
                {displayCases.map((c, i) => (
                  <tr key={i} className="border-b">
                    <td className="px-2 py-1.5">{c.trade_name || c.legal_name || 'N/A'}</td>
                    <td className="px-2 py-1.5">{[c.city, c.state].filter(Boolean).join(', ')}</td>
                    <td className="px-2 py-1.5 text-right">{c.violations_count || 0}</td>
                    <td className="px-2 py-1.5 text-right">{formatCurrency(c.backwages)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {cases.length > 5 && !showAll && (
          <Button variant="outline" size="sm" onClick={() => setShowAll(true)}>
            Show all {cases.length} cases
          </Button>
        )}
      </div>
    </CollapsibleCard>
  )
}
