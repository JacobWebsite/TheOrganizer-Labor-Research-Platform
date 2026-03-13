import { useState } from 'react'
import { ShieldAlert, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'

function formatCurrency(n) {
  if (n == null || n === 0) return '$0'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

function formatDate(d) {
  if (!d) return '--'
  return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

const SOURCE_LABELS = {
  debarment: 'Debarment',
  local_labor_law: 'Local Labor Law',
  wage_theft_nys: 'NYS Wage Theft',
}

export function NycEnforcementSection({ nycEnforcement }) {
  const [showAll, setShowAll] = useState(false)

  if (!nycEnforcement || !nycEnforcement.summary || nycEnforcement.summary.record_count === 0) {
    return (
      <CollapsibleCard icon={ShieldAlert} title="NYC Enforcement" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No NYC/NYS enforcement records have been matched to this employer. This does{' '}
            <strong>not</strong> mean no violations exist — it may mean the employer name did not
            match records in the NYC debarment list, local labor laws, or NYS wage theft databases.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const { summary, records = [] } = nycEnforcement
  const displayRecords = showAll ? records : records.slice(0, 10)

  return (
    <CollapsibleCard
      icon={ShieldAlert}
      title="NYC Enforcement"
      summary={`${summary.record_count} records`}
    >
      <div className="space-y-4">
        {/* Debarment badge */}
        {summary.is_debarred && (
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold bg-red-100 text-red-800">
              <ShieldAlert className="h-3 w-3" />
              DEBARRED
              {summary.debarment_end_date && ` (until ${formatDate(summary.debarment_end_date)})`}
            </span>
          </div>
        )}

        {/* Summary stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground">Records</span>
            <div className="font-medium">{summary.record_count}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Debarred</span>
            <div className="font-medium">{summary.is_debarred ? 'Yes' : 'No'}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Wages Owed</span>
            <div className="font-medium">{formatCurrency(summary.total_wages_owed)}</div>
          </div>
          <div>
            <span className="text-muted-foreground">Recovered</span>
            <div className="font-medium">{formatCurrency(summary.total_recovered)}</div>
          </div>
        </div>

        {/* Detail table */}
        {records.length > 0 && (
          <div className="overflow-x-auto border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-2 py-1.5 text-left font-medium">Source</th>
                  <th className="px-2 py-1.5 text-left font-medium">Employer Name</th>
                  <th className="px-2 py-1.5 text-left font-medium">Date</th>
                  <th className="px-2 py-1.5 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {displayRecords.map((r, i) => (
                  <tr key={i} className="border-b">
                    <td className="px-2 py-1.5">{SOURCE_LABELS[r.source] || r.source}</td>
                    <td className="px-2 py-1.5">{r.employer_name || 'N/A'}</td>
                    <td className="px-2 py-1.5">{formatDate(r.debarment_start_date)}</td>
                    <td className="px-2 py-1.5 text-right">{r.amount ? formatCurrency(r.amount) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {records.length > 10 && !showAll && (
          <Button variant="outline" size="sm" onClick={() => setShowAll(true)}>
            Show all {records.length} records
          </Button>
        )}
      </div>
    </CollapsibleCard>
  )
}
