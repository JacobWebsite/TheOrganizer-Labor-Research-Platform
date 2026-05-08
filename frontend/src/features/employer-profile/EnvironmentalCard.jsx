import { useState } from 'react'
import { Leaf, AlertTriangle, Loader2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { SourceFreshnessFooter } from '@/shared/components/SourceFreshnessFooter'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useMasterEpaEcho } from '@/shared/api/profile'

// 24Q-31: EnvironmentalCard. Mirrors the OshaSection pattern (summary
// stats + truncated facility table + freshness footer) using the EPA ECHO
// data linked to a master employer through master_employer_source_ids.
//
// Self-fetches via useMasterEpaEcho(masterId). The card is self-contained
// so the parent page only needs to pass `masterId`.

const VISIBLE_ROWS = 5

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null) return '\u2014'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

function formatVintageDate(d) {
  if (!d) return null
  try {
    const parsed = new Date(d)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return null
  }
}

function FlagBadge({ label, count, variant = 'default' }) {
  if (!count) return null
  const colors = {
    snc: 'bg-red-100 text-red-800 border-red-300',
    formal: 'bg-orange-100 text-orange-800 border-orange-300',
    informal: 'bg-yellow-100 text-yellow-800 border-yellow-300',
    default: 'bg-muted text-muted-foreground border-muted-foreground/30',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-medium',
        colors[variant] || colors.default,
      )}
    >
      {label}: {formatNumber(count)}
    </span>
  )
}

export function EnvironmentalCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError } = useMasterEpaEcho(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={Leaf} title="EPA Environmental Record" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading EPA enforcement data...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={Leaf} title="EPA Environmental Record" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load EPA ECHO data. The data may still be loading on the server.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const facilities = data?.facilities || []

  // No data path: same pattern as OshaSection -- show explicit "no records
  // matched" panel rather than hiding the card. This is critical for the
  // "no data != no violations" UX problem.
  if (!summary.total_facilities && facilities.length === 0) {
    return (
      <CollapsibleCard icon={Leaf} title="EPA Environmental Record" summary="No records matched">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            No EPA ECHO facilities have been matched to this employer. This does <strong>not</strong>{' '}
            mean no environmental violations exist &mdash; it may mean our matching has not yet
            connected this employer to EPA enforcement records.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(summary.total_facilities)} facilities \u00b7 ${formatCurrency(summary.total_penalties)} penalties`
  const visibleFacilities = expanded ? facilities : facilities.slice(0, VISIBLE_ROWS)
  const hasMore = facilities.length > VISIBLE_ROWS
  const vintageDate = formatVintageDate(data?.latest_record_date)

  return (
    <CollapsibleCard icon={Leaf} title="EPA Environmental Record" summary={summaryText}>
      <div className="space-y-4">
        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_facilities)}</div>
            <div className="text-xs text-muted-foreground">Facilities</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_inspections)}</div>
            <div className="text-xs text-muted-foreground">Inspections</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatNumber(summary.total_formal_actions)}</div>
            <div className="text-xs text-muted-foreground">Formal Actions</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatCurrency(summary.total_penalties)}</div>
            <div className="text-xs text-muted-foreground">Total Penalties</div>
          </div>
        </div>

        {/* Severity badges */}
        {(summary.snc_facilities || summary.total_formal_actions || summary.total_informal_actions) ? (
          <div className="flex flex-wrap gap-2">
            <FlagBadge label="significant non-compliers" count={summary.snc_facilities} variant="snc" />
            <FlagBadge label="formal actions" count={summary.total_formal_actions} variant="formal" />
            <FlagBadge label="informal actions" count={summary.total_informal_actions} variant="informal" />
          </div>
        ) : null}

        {/* Facilities table */}
        {facilities.length > 0 && (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Facility</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">City</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Inspections</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Formal Actions</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Penalties</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFacilities.map((f, i) => (
                    <tr key={f.registry_id || i} className="border-b">
                      <td className="px-3 py-2 font-medium">
                        {f.facility_name || '\u2014'}
                        {f.snc_flag && (
                          <span
                            className="ml-2 inline-flex items-center border border-red-300 bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700"
                            title="Significant Non-Complier (EPA designation)"
                          >
                            SNC
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">{f.city || '\u2014'}</td>
                      <td className="px-3 py-2">{f.state || '\u2014'}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(f.inspection_count)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(f.formal_action_count)}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(f.total_penalties)}</td>
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
                {expanded ? 'Show less' : `Show all ${facilities.length} facilities`}
              </Button>
            )}
          </>
        )}

        {vintageDate && (
          <p className="text-xs text-muted-foreground">
            EPA data current through {vintageDate}
          </p>
        )}
        <SourceFreshnessFooter
          sourceName="epa_echo"
          latestRecordDate={data?.latest_record_date}
        />
      </div>
    </CollapsibleCard>
  )
}
