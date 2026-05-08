import { useState } from 'react'
import { TrendingUp, AlertTriangle, Loader2 } from 'lucide-react'
import { CollapsibleCard } from '@/shared/components/CollapsibleCard'
import { Button } from '@/components/ui/button'
import { useMasterInstitutionalOwners } from '@/shared/api/profile'

// 24Q-9: InstitutionalOwnersCard. Surfaces the SEC Form 13F institutional
// ownership data on the master profile -- "who owns this firm's stock?"
// Q9 Stockholders moves Missing -> Strong.
//
// Per UX direction (same as ExecutivesCard): minimal chrome. Names + value
// + shares + period. No tier badges, no rank chart, no charts.

const VISIBLE_ROWS = 10

function formatNumber(n) {
  if (n == null) return '\u2014'
  return Number(n).toLocaleString()
}

function formatCurrency(n) {
  if (n == null || n === 0) return '\u2014'
  // Use compact notation for >$1M to avoid wide columns
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

function formatPeriodLabel(d) {
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

export function InstitutionalOwnersCard({ masterId }) {
  const [expanded, setExpanded] = useState(false)
  const { data, isLoading, isError } = useMasterInstitutionalOwners(masterId)

  if (isLoading) {
    return (
      <CollapsibleCard icon={TrendingUp} title="Institutional Owners" summary="Loading...">
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading SEC 13F institutional ownership...</span>
        </div>
      </CollapsibleCard>
    )
  }

  if (isError) {
    return (
      <CollapsibleCard icon={TrendingUp} title="Institutional Owners" summary="Error">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>Could not load SEC 13F data.</p>
        </div>
      </CollapsibleCard>
    )
  }

  const summary = data?.summary || {}
  const owners = data?.owners || []

  // No-match path: this employer doesn't appear as an issuer in 13F. The
  // most common reason is the company is private (or the master row is
  // private). Show explicit explanation rather than hiding the card.
  if (!summary.is_matched) {
    return (
      <CollapsibleCard
        icon={TrendingUp}
        title="Institutional Owners"
        summary="Not in 13F (likely private)"
      >
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            This employer is not currently matched to any SEC Form 13F issuer. 13F coverage
            is limited to publicly-traded U.S. companies. If this employer is publicly traded
            and you expected to see institutional owners here, the issuer name in 13F may
            differ from our canonical name &mdash; flag it for re-matching.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  // Matched but no holdings yet (e.g. just-filed). Edge case.
  if (!summary.total_owners) {
    return (
      <CollapsibleCard icon={TrendingUp} title="Institutional Owners" summary="No holdings reported">
        <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
          <p>
            Matched as 13F issuer <strong>{summary.issuer_name_used}</strong> but no
            institutional holdings are reported in our latest data window.
          </p>
        </div>
      </CollapsibleCard>
    )
  }

  const summaryText = `${formatNumber(summary.total_owners)} institutional owner${summary.total_owners === 1 ? '' : 's'} \u00b7 ${formatCurrency(summary.total_value)}`
  const visibleOwners = expanded ? owners : owners.slice(0, VISIBLE_ROWS)
  const hasMore = owners.length > VISIBLE_ROWS
  const periodLabel = formatPeriodLabel(summary.latest_period)

  return (
    <CollapsibleCard icon={TrendingUp} title="Institutional Owners" summary={summaryText}>
      <div className="space-y-4">
        {/* Caveat note. Sort order is value DESC. */}
        <p className="text-xs italic text-muted-foreground">
          SEC Form 13F filings as of {periodLabel || 'most recent quarter'}. Top institutional
          investors with reported stakes in <strong>{summary.issuer_name_used}</strong>.
          {summary.match_method === 'trigram' && summary.match_confidence != null && (
            <>
              {' '}Issuer matched by name similarity (confidence{' '}
              {Math.round(summary.match_confidence * 100)}%).
            </>
          )}
        </p>

        {owners.length > 0 && (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Filer</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">State</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Stake Value</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Shares</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleOwners.map((o, i) => (
                    <tr key={`${o.filer_cik}-${i}`} className="border-b">
                      <td className="px-3 py-2 font-medium">{o.filer_name || '\u2014'}</td>
                      <td className="px-3 py-2 text-xs">{o.filer_state || '\u2014'}</td>
                      <td className="px-3 py-2 text-right">{formatCurrency(o.value)}</td>
                      <td className="px-3 py-2 text-right">{o.shares ? formatNumber(o.shares) : '\u2014'}</td>
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
                {expanded
                  ? 'Show top 10 only'
                  : `Show all ${owners.length} owners (sorted by stake value)`}
              </Button>
            )}
            {owners.length < summary.total_owners && (
              <p className="text-xs text-muted-foreground">
                Showing top {owners.length} of {formatNumber(summary.total_owners)} total
                institutional filers.
              </p>
            )}
          </>
        )}

        {periodLabel && (
          <p className="text-xs text-muted-foreground">
            13F data current through {periodLabel}
          </p>
        )}
      </div>
    </CollapsibleCard>
  )
}
