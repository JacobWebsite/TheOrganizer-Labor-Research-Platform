import { useState } from 'react'
import { ShieldAlert, AlertTriangle } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceAttribution } from '@/shared/components/SourceAttribution'
import { DataSourceBadge } from '@/shared/components/DataSourceBadge'
import { SourceFreshnessFooter } from '@/shared/components/SourceFreshnessFooter'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const VISIBLE_ROWS = 5

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

function formatVintageDate(d) {
  if (!d) return null
  try {
    const parsed = new Date(d)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return null
  }
}

function SeverityBadge({ label, count }) {
  if (!count) return null
  const colors = {
    serious: 'bg-orange-100 text-orange-800 border-orange-300',
    willful: 'bg-red-100 text-red-800 border-red-300',
    repeat: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  }
  return (
    <span className={cn('inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-medium', colors[label] || 'bg-muted')}>
      {label}: {formatNumber(count)}
    </span>
  )
}

export function OshaSection({ osha, sourceAttribution, dataSources }) {
  const [expanded, setExpanded] = useState(false)

  const summary = osha?.summary || {}
  const establishments = osha?.establishments || []

  // If no data at all, show warning instead of hiding
  if (!osha || (!summary.total_establishments && establishments.length === 0)) {
    return (
      <CollapsibleCard icon={ShieldAlert} title="OSHA Safety Record" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No OSHA records have been matched to this employer. This does <strong>not</strong> mean
            no violations exist — it may mean our matching has not yet connected this employer to
            OSHA inspection records.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(summary.total_violations)} violations \u00b7 ${formatCurrency(summary.total_penalties)} penalties`
  const visibleEstablishments = expanded ? establishments : establishments.slice(0, VISIBLE_ROWS)
  const hasMore = establishments.length > VISIBLE_ROWS
  const vintageDate = formatVintageDate(osha?.latest_record_date)

  return (
    <CollapsibleCard icon={ShieldAlert} title="OSHA Safety Record" summary={summaryText}>
      <div className="space-y-4">
        <SourceAttribution attribution={sourceAttribution} />
        {dataSources && (
          <DataSourceBadge
            source="OSHA"
            hasFlag={dataSources.has_osha}
            hasData={!!(osha?.establishments?.length > 0)}
          />
        )}
        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_establishments)}</div>
            <div className="text-xs text-muted-foreground">Establishments</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_inspections)}</div>
            <div className="text-xs text-muted-foreground">Inspections</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_violations)}</div>
            <div className="text-xs text-muted-foreground">Violations</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatCurrency(summary.total_penalties)}</div>
            <div className="text-xs text-muted-foreground">Total Penalties</div>
          </div>
        </div>

        {/* Severity badges */}
        {(summary.serious_violations || summary.willful_violations || summary.repeat_violations) && (
          <div className="flex flex-wrap gap-2">
            <SeverityBadge label="serious" count={summary.serious_violations} />
            <SeverityBadge label="willful" count={summary.willful_violations} />
            <SeverityBadge label="repeat" count={summary.repeat_violations} />
          </div>
        )}

        {/* Establishments table */}
        {establishments.length > 0 && (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Establishment</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">City</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Inspections</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Violations</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Penalties</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEstablishments.map((est, i) => (
                    <tr key={est.establishment_id || i} className="border-b">
                      <td className="px-3 py-2 font-medium">
                        {est.establishment_name || '\u2014'}
                        {est.score_eligible === false && (
                          <span className="ml-2 inline-flex items-center border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700" title={`Match: ${est.match_method || 'unknown'} (${(est.match_confidence * 100).toFixed(0)}%)`}>
                            Unverified match
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">{est.city || '\u2014'}</td>
                      <td className="px-3 py-2">{est.state || '\u2014'}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(est.inspection_count)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(est.violation_count)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(est.total_penalties)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasMore && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full"
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? 'Show less' : `Show all ${establishments.length} establishments`}
              </Button>
            )}
          </>
        )}

        {vintageDate && (
          <p className="text-xs text-muted-foreground">
            OSHA data current through {vintageDate}
          </p>
        )}
        <SourceFreshnessFooter
          sourceName="osha_workplace_safety"
          latestRecordDate={osha?.latest_record_date}
        />
      </div>
    </CollapsibleCard>
  )
}
